"""BDD tests for ARIS and Visio process model importers (Story #328).

Tests element extraction, sequence flows, swim lane role assignment,
and error handling for both ARIS AML and Visio VSDX formats.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from src.integrations.importers.aris_importer import ARISImporter
from src.integrations.importers.model_importer import (
    EdgeType,
    ElementType,
    ImportedModel,
    ImportFormatError,
    ProcessElement,
)
from src.integrations.importers.visio_importer import VisioImporter

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_AML = FIXTURES_DIR / "sample.aml"


def _create_vsdx(pages_xml: bytes, masters_xml: bytes | None = None) -> bytes:
    """Create a minimal VSDX ZIP archive for testing."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("visio/pages/page1.xml", pages_xml)
        if masters_xml:
            zf.writestr("visio/masters/masters.xml", masters_xml)
    return buf.getvalue()


VISIO_NS = "http://schemas.microsoft.com/office/visio/2012/main"

SAMPLE_MASTERS_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<Masters xmlns="{VISIO_NS}">
  <Master ID="1" Name="Process"/>
  <Master ID="2" Name="Decision"/>
  <Master ID="3" Name="Start"/>
  <Master ID="4" Name="End/Terminator"/>
  <Master ID="5" Name="Swimlane"/>
</Masters>""".encode()

SAMPLE_PAGE_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<PageContents xmlns="{VISIO_NS}">
  <Shapes>
    <Shape ID="10" Master="1">
      <Text>Submit Form</Text>
    </Shape>
    <Shape ID="11" Master="1">
      <Text>Review Form</Text>
    </Shape>
    <Shape ID="12" Master="2">
      <Text>Valid?</Text>
    </Shape>
    <Shape ID="13" Master="3">
      <Text>Start</Text>
    </Shape>
    <Shape ID="14" Master="4">
      <Text>End</Text>
    </Shape>
    <Shape ID="100">
      <Cell N="BeginX" V="1"/>
      <Cell N="EndX" V="2"/>
    </Shape>
    <Shape ID="101">
      <Cell N="BeginX" V="1"/>
      <Cell N="EndX" V="2"/>
    </Shape>
  </Shapes>
  <Connects>
    <Connect FromSheet="100" ToSheet="10" FromCell="BeginX"/>
    <Connect FromSheet="100" ToSheet="11" FromCell="EndX"/>
    <Connect FromSheet="101" ToSheet="11" FromCell="BeginX"/>
    <Connect FromSheet="101" ToSheet="12" FromCell="EndX"/>
  </Connects>
</PageContents>""".encode()


# --- ARIS AML Tests ---


class TestARISImportValidFile:
    """Scenario 1: ARIS AML/XML file import."""

    def test_parses_sample_aml(self) -> None:
        """Sample AML file is parsed with correct element count."""
        importer = ARISImporter()
        model = importer.parse(SAMPLE_AML)

        assert model.success
        assert model.element_count == 7  # 4 tasks + 1 gateway + 2 roles (as UNKNOWN)

    def test_elements_have_correct_types(self) -> None:
        """Elements classified to BPMN-equivalent types."""
        importer = ARISImporter()
        model = importer.parse(SAMPLE_AML)

        tasks = model.get_elements_by_type(ElementType.TASK)
        gateways = model.get_elements_by_type(ElementType.GATEWAY)
        events = model.get_elements_by_type(ElementType.INTERMEDIATE_EVENT)

        assert len(tasks) == 3  # Submit, Review, Approve
        assert len(gateways) == 1  # Approved?
        assert len(events) == 1  # Application Received

    def test_element_names_preserved(self) -> None:
        """Element names match ARIS model."""
        importer = ARISImporter()
        model = importer.parse(SAMPLE_AML)

        names = {e.name for e in model.elements}
        assert "Submit Application" in names
        assert "Review Application" in names
        assert "Approved?" in names

    def test_source_format_set(self) -> None:
        """source_format is aris_aml on all elements."""
        importer = ARISImporter()
        model = importer.parse(SAMPLE_AML)

        assert all(e.source_format == "aris_aml" for e in model.elements)
        assert model.source_format == "aris_aml"

    def test_sequence_flows_extracted(self) -> None:
        """PRECEDES edges created from CxnDef connections."""
        importer = ARISImporter()
        model = importer.parse(SAMPLE_AML)

        precedes = [e for e in model.edges if e.edge_type == EdgeType.PRECEDES]
        assert len(precedes) == 3  # obj-1->obj-2, obj-2->obj-3, obj-3->obj-4


class TestARISRoleAssignment:
    """Scenario 3: Swim lane role assignment from ARIS."""

    def test_performed_by_edges(self) -> None:
        """Role assignment connections create PERFORMED_BY edges."""
        importer = ARISImporter()
        model = importer.parse(SAMPLE_AML)

        performed_by = model.get_performed_by_edges()
        assert len(performed_by) == 2  # Clerk->obj-1, Manager->obj-2

    def test_roles_extracted(self) -> None:
        """Role names added to model.roles."""
        importer = ARISImporter()
        model = importer.parse(SAMPLE_AML)

        assert "Clerk" in model.roles
        assert "Manager" in model.roles

    def test_lane_assignment(self) -> None:
        """Elements assigned to lanes."""
        importer = ARISImporter()
        model = importer.parse(SAMPLE_AML)

        elem_map = {e.id: e for e in model.elements}
        assert elem_map["obj-1"].lane == "Front Office"
        assert elem_map["obj-2"].lane == "Back Office"


class TestARISErrorHandling:
    """Scenario 4: Error handling for ARIS files."""

    def test_file_not_found(self) -> None:
        """Missing file returns error result."""
        importer = ARISImporter()
        model = importer.parse("/nonexistent/file.aml")

        assert not model.success
        assert "not found" in model.errors[0]

    def test_wrong_extension(self, tmp_path: Path) -> None:
        """Non-AML extension returns error."""
        wrong_ext = tmp_path / "file.bpmn"
        wrong_ext.write_text("content")

        importer = ARISImporter()
        model = importer.parse(wrong_ext)

        assert not model.success
        assert "Unsupported file extension" in model.errors[0]

    def test_malformed_xml(self, tmp_path: Path) -> None:
        """Invalid XML returns parse error."""
        bad_file = tmp_path / "bad.aml"
        bad_file.write_text("<invalid xml!!!!!")

        importer = ARISImporter()
        model = importer.parse(bad_file)

        assert not model.success
        assert "XML parse error" in model.errors[0]

    def test_unsupported_version(self, tmp_path: Path) -> None:
        """Unsupported ARIS version raises ImportFormatError."""
        aml = tmp_path / "v8.aml"
        aml.write_text('<?xml version="1.0"?><AML Version="8.0"></AML>')

        importer = ARISImporter()
        with pytest.raises(ImportFormatError) as exc_info:
            importer.parse(aml)

        err = exc_info.value
        assert err.format_name == "aris_aml"
        assert err.detected_version == "8.0"
        assert "9.x" in err.supported_versions

    def test_version_1x_rejected(self, tmp_path: Path) -> None:
        """Version 1.x is not in supported 9.x/10.x range."""
        aml = tmp_path / "v1.aml"
        aml.write_text('<?xml version="1.0"?><AML Version="1.0"></AML>')

        importer = ARISImporter()
        with pytest.raises(ImportFormatError) as exc_info:
            importer.parse(aml)

        assert exc_info.value.detected_version == "1.0"

    def test_version_11x_rejected(self, tmp_path: Path) -> None:
        """Version 11.x is not in supported 9.x/10.x range."""
        aml = tmp_path / "v11.aml"
        aml.write_text('<?xml version="1.0"?><AML Version="11.0"></AML>')

        importer = ARISImporter()
        with pytest.raises(ImportFormatError) as exc_info:
            importer.parse(aml)

        assert exc_info.value.detected_version == "11.0"


# --- Visio VSDX Tests ---


class TestVisioImportValidFile:
    """Scenario 2: Visio VSDX file import with shape mapping."""

    def test_parses_vsdx(self, tmp_path: Path) -> None:
        """VSDX file is parsed with correct element count."""
        vsdx_path = tmp_path / "process.vsdx"
        vsdx_path.write_bytes(_create_vsdx(SAMPLE_PAGE_XML, SAMPLE_MASTERS_XML))

        importer = VisioImporter()
        model = importer.parse(vsdx_path)

        assert model.success
        # 5 shapes: 2 Process + 1 Decision + 1 Start + 1 End
        assert model.element_count == 5

    def test_shape_type_classification(self, tmp_path: Path) -> None:
        """Shapes classified by master name to BPMN types."""
        vsdx_path = tmp_path / "process.vsdx"
        vsdx_path.write_bytes(_create_vsdx(SAMPLE_PAGE_XML, SAMPLE_MASTERS_XML))

        importer = VisioImporter()
        model = importer.parse(vsdx_path)

        tasks = model.get_elements_by_type(ElementType.TASK)
        gateways = model.get_elements_by_type(ElementType.GATEWAY)
        start_events = model.get_elements_by_type(ElementType.START_EVENT)
        end_events = model.get_elements_by_type(ElementType.END_EVENT)

        assert len(tasks) == 2  # Submit Form, Review Form
        assert len(gateways) == 1  # Valid?
        assert len(start_events) == 1
        assert len(end_events) == 1

    def test_shape_text_as_name(self, tmp_path: Path) -> None:
        """Shape text label becomes element name."""
        vsdx_path = tmp_path / "process.vsdx"
        vsdx_path.write_bytes(_create_vsdx(SAMPLE_PAGE_XML, SAMPLE_MASTERS_XML))

        importer = VisioImporter()
        model = importer.parse(vsdx_path)

        names = {e.name for e in model.elements}
        assert "Submit Form" in names
        assert "Review Form" in names
        assert "Valid?" in names

    def test_connection_arrows_create_edges(self, tmp_path: Path) -> None:
        """Connector shapes create PRECEDES edges."""
        vsdx_path = tmp_path / "process.vsdx"
        vsdx_path.write_bytes(_create_vsdx(SAMPLE_PAGE_XML, SAMPLE_MASTERS_XML))

        importer = VisioImporter()
        model = importer.parse(vsdx_path)

        precedes = [e for e in model.edges if e.edge_type == EdgeType.PRECEDES]
        assert len(precedes) == 2  # 10->11, 11->12

    def test_source_format_set(self, tmp_path: Path) -> None:
        """source_format is visio_vsdx."""
        vsdx_path = tmp_path / "process.vsdx"
        vsdx_path.write_bytes(_create_vsdx(SAMPLE_PAGE_XML, SAMPLE_MASTERS_XML))

        importer = VisioImporter()
        model = importer.parse(vsdx_path)

        assert model.source_format == "visio_vsdx"
        assert all(e.source_format == "visio_vsdx" for e in model.elements)


class TestVisioSwimLanes:
    """Scenario 3: Swim lane role assignment from Visio."""

    def test_lane_shapes_with_children(self, tmp_path: Path) -> None:
        """Swim lane containers assign roles to child shapes."""
        page_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <PageContents xmlns="{VISIO_NS}">
          <Shapes>
            <Shape ID="50" Master="5">
              <Text>Operations</Text>
              <Shapes>
                <Shape ID="51" Master="1">
                  <Text>Process Order</Text>
                </Shape>
              </Shapes>
            </Shape>
          </Shapes>
        </PageContents>""".encode()

        vsdx_path = tmp_path / "lanes.vsdx"
        vsdx_path.write_bytes(_create_vsdx(page_xml, SAMPLE_MASTERS_XML))

        importer = VisioImporter()
        model = importer.parse(vsdx_path)

        assert "Operations" in model.roles

        performed_by = model.get_performed_by_edges()
        assert len(performed_by) >= 1
        assert any(e.label == "Operations" for e in performed_by)


class TestVisioErrorHandling:
    """Scenario 4: Error handling for Visio files."""

    def test_file_not_found(self) -> None:
        """Missing file returns error result."""
        importer = VisioImporter()
        model = importer.parse("/nonexistent/file.vsdx")

        assert not model.success
        assert "not found" in model.errors[0]

    def test_wrong_extension(self, tmp_path: Path) -> None:
        """Non-VSDX extension returns error."""
        wrong_ext = tmp_path / "file.docx"
        wrong_ext.write_text("content")

        importer = VisioImporter()
        model = importer.parse(wrong_ext)

        assert not model.success
        assert "Unsupported file extension" in model.errors[0]

    def test_corrupt_zip(self, tmp_path: Path) -> None:
        """Corrupted ZIP raises ImportFormatError."""
        bad_file = tmp_path / "corrupt.vsdx"
        bad_file.write_bytes(b"not a zip file at all")

        importer = VisioImporter()
        with pytest.raises(ImportFormatError) as exc_info:
            importer.parse(bad_file)

        assert exc_info.value.format_name == "visio_vsdx"
        assert "ZIP" in str(exc_info.value)

    def test_missing_pages(self, tmp_path: Path) -> None:
        """VSDX without pages/ raises ImportFormatError."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("visio/document.xml", "<doc/>")
        vsdx_path = tmp_path / "nopages.vsdx"
        vsdx_path.write_bytes(buf.getvalue())

        importer = VisioImporter()
        with pytest.raises(ImportFormatError):
            importer.parse(vsdx_path)


# --- Shared Model Tests ---


class TestImportedModelDataStructure:
    """ImportedModel data structure."""

    def test_success_flag(self) -> None:
        model = ImportedModel()
        assert not model.success  # No elements

        model.elements.append(
            ProcessElement(id="1", name="Test", element_type=ElementType.TASK)
        )
        assert model.success

    def test_success_false_with_errors(self) -> None:
        model = ImportedModel(errors=["something wrong"])
        model.elements.append(
            ProcessElement(id="1", name="Test", element_type=ElementType.TASK)
        )
        assert not model.success

    def test_get_elements_by_type(self) -> None:
        model = ImportedModel(
            elements=[
                ProcessElement(id="1", name="A", element_type=ElementType.TASK),
                ProcessElement(id="2", name="B", element_type=ElementType.GATEWAY),
                ProcessElement(id="3", name="C", element_type=ElementType.TASK),
            ]
        )
        assert len(model.get_elements_by_type(ElementType.TASK)) == 2
        assert len(model.get_elements_by_type(ElementType.GATEWAY)) == 1

    def test_import_format_error_attributes(self) -> None:
        err = ImportFormatError(
            "Bad format",
            format_name="aris_aml",
            detected_version="7.0",
            supported_versions=["9.x", "10.x"],
        )
        assert err.format_name == "aris_aml"
        assert err.detected_version == "7.0"
        assert "9.x" in err.supported_versions
        assert "7.0" in str(err)
        assert "Supported" in str(err)
