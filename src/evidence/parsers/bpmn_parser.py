"""BPMN 2.0 XML parser for process model evidence.

Extracts activities, gateways, sequence flows, and swimlanes from
BPMN 2.0 XML files and creates process_element fragments.
"""

from __future__ import annotations

import logging
from pathlib import Path

from lxml import etree

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)

# BPMN 2.0 namespace
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMN_NSMAP = {"bpmn": BPMN_NS}


class BpmnParser(BaseParser):
    """Parser for BPMN 2.0 XML process model files."""

    supported_formats = [".bpmn", ".bpmn2", ".xml"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a BPMN file and extract process elements.

        Extracts:
        - Tasks (user, service, script, manual, etc.)
        - Gateways (exclusive, parallel, inclusive, etc.)
        - Events (start, end, intermediate)
        - Sequence flows
        - Participants / lanes (swimlanes)
        """
        ext = Path(file_name).suffix.lower()
        if ext not in self.supported_formats:
            return ParseResult(error=f"Unsupported BPMN format: {ext}")

        try:
            return await self._parse_bpmn(file_path)
        except Exception as e:
            logger.exception("Failed to parse BPMN: %s", file_name)
            return ParseResult(error=f"Parse error: {e}")

    async def _parse_bpmn(self, file_path: str) -> ParseResult:
        """Parse a BPMN XML file and extract process elements."""
        fragments: list[ParsedFragment] = []
        metadata: dict[str, str | int | float | bool | None] = {}

        tree = etree.parse(file_path)  # noqa: S320
        root = tree.getroot()

        # Detect namespace from root
        nsmap = self._detect_namespace(root)

        # Extract processes
        processes = root.findall(f".//{{{nsmap['bpmn']}}}process") if "bpmn" in nsmap else []
        metadata["process_count"] = len(processes)

        task_count = 0
        gateway_count = 0
        event_count = 0
        flow_count = 0

        for process in processes:
            process_id = process.get("id", "unknown")
            process_name = process.get("name", process_id)

            # Extract tasks
            task_types = [
                "task",
                "userTask",
                "serviceTask",
                "scriptTask",
                "manualTask",
                "sendTask",
                "receiveTask",
                "businessRuleTask",
                "subProcess",
            ]
            for task_type in task_types:
                for task in process.findall(f".//{{{nsmap['bpmn']}}}{task_type}"):
                    task_name = task.get("name", task.get("id", "unnamed"))
                    task_id = task.get("id", "")
                    fragments.append(
                        ParsedFragment(
                            fragment_type=FragmentType.PROCESS_ELEMENT,
                            content=f"{task_type}: {task_name}",
                            metadata={
                                "element_type": task_type,
                                "element_id": task_id,
                                "process_id": process_id,
                                "process_name": process_name,
                            },
                        )
                    )
                    task_count += 1

            # Extract gateways
            gateway_types = [
                "exclusiveGateway",
                "parallelGateway",
                "inclusiveGateway",
                "eventBasedGateway",
                "complexGateway",
            ]
            for gw_type in gateway_types:
                for gateway in process.findall(f".//{{{nsmap['bpmn']}}}{gw_type}"):
                    gw_name = gateway.get("name", gateway.get("id", "unnamed"))
                    gw_id = gateway.get("id", "")
                    fragments.append(
                        ParsedFragment(
                            fragment_type=FragmentType.PROCESS_ELEMENT,
                            content=f"{gw_type}: {gw_name}",
                            metadata={
                                "element_type": gw_type,
                                "element_id": gw_id,
                                "process_id": process_id,
                            },
                        )
                    )
                    gateway_count += 1

            # Extract events
            event_types = [
                "startEvent",
                "endEvent",
                "intermediateThrowEvent",
                "intermediateCatchEvent",
                "boundaryEvent",
            ]
            for ev_type in event_types:
                for event in process.findall(f".//{{{nsmap['bpmn']}}}{ev_type}"):
                    ev_name = event.get("name", event.get("id", "unnamed"))
                    ev_id = event.get("id", "")
                    fragments.append(
                        ParsedFragment(
                            fragment_type=FragmentType.PROCESS_ELEMENT,
                            content=f"{ev_type}: {ev_name}",
                            metadata={
                                "element_type": ev_type,
                                "element_id": ev_id,
                                "process_id": process_id,
                            },
                        )
                    )
                    event_count += 1

            # Extract sequence flows as relationships
            for flow in process.findall(f".//{{{nsmap['bpmn']}}}sequenceFlow"):
                source = flow.get("sourceRef", "")
                target = flow.get("targetRef", "")
                flow_name = flow.get("name", "")
                flow_id = flow.get("id", "")
                fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.RELATIONSHIP,
                        content=f"flow: {source} -> {target}" + (f" [{flow_name}]" if flow_name else ""),
                        metadata={
                            "element_type": "sequenceFlow",
                            "element_id": flow_id,
                            "source_ref": source,
                            "target_ref": target,
                            "process_id": process_id,
                        },
                    )
                )
                flow_count += 1

        # Extract participants (pools/lanes)
        collaborations = root.findall(f".//{{{nsmap['bpmn']}}}collaboration") if "bpmn" in nsmap else []
        for collab in collaborations:
            for participant in collab.findall(f".//{{{nsmap['bpmn']}}}participant"):
                part_name = participant.get("name", participant.get("id", "unnamed"))
                part_id = participant.get("id", "")
                fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.PROCESS_ELEMENT,
                        content=f"participant: {part_name}",
                        metadata={
                            "element_type": "participant",
                            "element_id": part_id,
                        },
                    )
                )

        # Extract lanes
        for lane_set in root.findall(f".//{{{nsmap.get('bpmn', BPMN_NS)}}}laneSet"):
            for lane in lane_set.findall(f".//{{{nsmap.get('bpmn', BPMN_NS)}}}lane"):
                lane_name = lane.get("name", lane.get("id", "unnamed"))
                lane_id = lane.get("id", "")
                fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.PROCESS_ELEMENT,
                        content=f"lane: {lane_name}",
                        metadata={
                            "element_type": "lane",
                            "element_id": lane_id,
                        },
                    )
                )

        metadata["task_count"] = task_count
        metadata["gateway_count"] = gateway_count
        metadata["event_count"] = event_count
        metadata["flow_count"] = flow_count

        return ParseResult(fragments=fragments, metadata=metadata)

    def _detect_namespace(self, root: etree._Element) -> dict[str, str]:
        """Detect the BPMN namespace from the root element.

        Handles both standard and Camunda namespaced BPMN files.
        """
        nsmap: dict[str, str] = {}

        # Check root tag namespace
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0].strip("{")
            if "bpmn" in ns.lower() or "omg.org" in ns:
                nsmap["bpmn"] = ns

        # Check explicit namespaces
        for _prefix, uri in (root.nsmap or {}).items():
            if uri and ("bpmn" in uri.lower() or "omg.org/spec/BPMN" in uri):
                nsmap["bpmn"] = uri
                break

        # Fallback to standard namespace
        if "bpmn" not in nsmap:
            nsmap["bpmn"] = BPMN_NS

        return nsmap
