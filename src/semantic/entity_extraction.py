"""Entity extraction service for evidence fragments.

Extracts typed entities (Activities, Decisions, Roles, Systems, Documents)
from text using rule-based NLP patterns as the MVP fallback. An LLM-based
extraction path (Claude API) can be plugged in for higher accuracy.

Each entity has a type, name, confidence score, and source span.
Entity resolution detects when different names refer to the same entity.
"""

from __future__ import annotations

import enum
import hashlib
import re
from dataclasses import dataclass, field


class EntityType(enum.StrEnum):
    """Types of entities extractable from evidence text."""

    ACTIVITY = "activity"
    DECISION = "decision"
    ROLE = "role"
    SYSTEM = "system"
    DOCUMENT = "document"


@dataclass
class ExtractedEntity:
    """A single entity extracted from text.

    Attributes:
        id: Unique identifier for the entity.
        entity_type: The category of entity.
        name: Canonical name of the entity.
        confidence: Confidence score from 0.0 to 1.0.
        source_span: The original text span that was matched.
        aliases: Alternate names that resolved to this entity.
        metadata: Additional extraction metadata.
    """

    id: str
    entity_type: EntityType
    name: str
    confidence: float
    source_span: str = ""
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class DuplicateCandidate:
    """A pair of entities flagged as potential duplicates.

    Attributes:
        entity_a_id: ID of the first entity.
        entity_b_id: ID of the second entity.
        entity_a_name: Name of the first entity.
        entity_b_name: Name of the second entity.
        entity_type: Shared entity type.
        similarity_reason: Why these were flagged as duplicates.
    """

    entity_a_id: str
    entity_b_id: str
    entity_a_name: str
    entity_b_name: str
    entity_type: EntityType
    similarity_reason: str


@dataclass
class ExtractionResult:
    """Result from running entity extraction on a text fragment.

    Attributes:
        entities: List of extracted entities.
        fragment_id: ID of the source fragment (if applicable).
        raw_text_length: Length of the input text.
    """

    entities: list[ExtractedEntity] = field(default_factory=list)
    fragment_id: str | None = None
    raw_text_length: int = 0


# ---------------------------------------------------------------------------
# Rule-based extraction patterns
# ---------------------------------------------------------------------------

# Activity patterns: verb + object phrases (imperative or gerund forms)
_ACTIVITY_PATTERNS: list[re.Pattern[str]] = [
    # Imperative: "Create Purchase Requisition", "Approve Invoice"
    re.compile(
        r"\b(Create|Submit|Approve|Review|Process|Validate|Verify|Execute|Perform|"
        r"Generate|Complete|Update|Send|Receive|Record|Prepare|Assess|Evaluate|"
        r"Initiate|Authorize|Reject|Cancel|Close|Open|Assign|Escalate|Monitor|"
        r"Audit|Reconcile|Notify|Request|Transfer|Archive|Retrieve|Publish|"
        r"Analyze|Configure|Deploy|Test|Sign|Route|Classify|Calculate|"
        r"Distribute|Collect|Upload|Download|Merge|Split|Consolidate|"
        r"Register|Enroll|Onboard|Offboard|Terminate|Suspend|Reactivate)"
        r"\s+([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){0,4})",
        re.MULTILINE,
    ),
    # Gerund: "creating purchase orders", "processing invoices"
    re.compile(
        r"\b(creating|submitting|approving|reviewing|processing|validating|"
        r"verifying|executing|performing|generating|completing|updating|"
        r"sending|receiving|recording|preparing|assessing|evaluating)"
        r"\s+(?:the\s+)?([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})",
        re.IGNORECASE | re.MULTILINE,
    ),
]

# Role patterns: title-like phrases
_ROLE_PATTERNS: list[re.Pattern[str]] = [
    # Explicit titles: "Procurement Specialist", "IT Manager", "Chief Financial Officer"
    re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+"
        r"(?:Manager|Director|Officer|Specialist|Analyst|Coordinator|"
        r"Administrator|Supervisor|Lead|Engineer|Architect|Consultant|"
        r"Auditor|Controller|Representative|Assistant|Clerk|Technician|"
        r"Advisor|Planner|Developer|Designer|Scientist|Strategist))\b"
    ),
    # Role references: "the approver", "the reviewer"
    re.compile(
        r"\bthe\s+(approver|reviewer|requestor|requester|submitter|"
        r"authorizer|administrator|operator|owner|custodian|manager|"
        r"processor|validator|verifier|auditor|controller|coordinator)\b",
        re.IGNORECASE,
    ),
    # Dept + role: "Finance Team", "IT Department"
    re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+"
        r"(?:Team|Department|Group|Division|Unit|Committee|Board))\b"
    ),
]

# System patterns: proper nouns + "system" or known system keywords
# NOTE: The "Noun + system" pattern does NOT use re.IGNORECASE because
# the capture group relies on uppercase detection to identify proper nouns.
# The keyword alternatives include both cases where needed.
_SYSTEM_PATTERNS: list[re.Pattern[str]] = [
    # Known enterprise systems (standalone references) - checked first for higher confidence
    re.compile(
        r"\b(SAP|Oracle|Salesforce|Workday|ServiceNow|Jira|Confluence|"
        r"SharePoint|Teams|Slack|Tableau|Power\s?BI|Snowflake|AWS|Azure|"
        r"GCP|Kubernetes|Jenkins|GitHub|GitLab|Splunk|Datadog|PeopleSoft|"
        r"Dynamics\s?365|NetSuite|Coupa|Ariba|Concur|SuccessFactors|"
        r"HubSpot|Marketo|Zendesk|Freshdesk|Asana|Monday|Notion)\b"
    ),
    # "SAP system", "Oracle ERP", "Workday platform"
    # No re.IGNORECASE so that [A-Z] correctly requires uppercase in the name
    re.compile(
        r"\b([A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)*)\s+"
        r"(?:[Ss]ystem|[Pp]latform|[Aa]pplication|[Ss]oftware|[Tt]ool|[Mm]odule|"
        r"[Ss]olution|[Pp]ortal|[Dd]atabase|[Ss]erver|[Ss]ervice|[Ii]nterface|[Ee]ngine)\b"
    ),
]

# Decision patterns: conditional logic
_DECISION_PATTERNS: list[re.Pattern[str]] = [
    # "if threshold exceeds", "when approved by"
    re.compile(
        r"\b(if|when|where|unless|provided\s+that|in\s+case)\s+"
        r"(.{5,80}?)(?:\s*,|\s*then|\s*:|\.\s)",
        re.IGNORECASE | re.MULTILINE,
    ),
    # "decision to approve/reject"
    re.compile(
        r"\b(?:decision|determine|decide|evaluate\s+whether)\s+"
        r"(?:to\s+|whether\s+)?(.{5,60}?)(?:\.|,|\s+and\s+|\s+or\s+)",
        re.IGNORECASE | re.MULTILINE,
    ),
    # Threshold/limit patterns
    re.compile(
        r"\b(?:threshold|limit|criteria|condition|rule)\s+"
        r"(?:of|for|is|exceeds?|below|above)\s+(.{3,60}?)(?:\.|,)",
        re.IGNORECASE | re.MULTILINE,
    ),
]

# Document patterns
_DOCUMENT_PATTERNS: list[re.Pattern[str]] = [
    # Named documents: "Purchase Order", "Invoice", "Contract"
    re.compile(
        r"\b((?:Purchase\s+Order|Invoice|Contract|Agreement|Policy|"
        r"Procedure|Manual|Guideline|Standard|Report|Template|Form|"
        r"Certificate|License|Permit|Statement|Receipt|Voucher|"
        r"Memo|Memorandum|Charter|Specification|Requirement|"
        r"Work\s+Order|Service\s+Level\s+Agreement|SLA|"
        r"Request\s+for\s+Proposal|RFP|Request\s+for\s+Quotation|RFQ|"
        r"Bill\s+of\s+Materials|BOM|Bill\s+of\s+Lading|BOL|"
        r"Terms\s+of\s+Reference|TOR|Statement\s+of\s+Work|SOW)"
        r"(?:\s+\#?\d+)?)\b",
        re.IGNORECASE,
    ),
]


def _generate_entity_id(entity_type: str, name: str) -> str:
    """Generate a deterministic entity ID from type and normalized name."""
    normalized = name.strip().lower()
    hash_input = f"{entity_type}:{normalized}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


def _clean_entity_name(name: str) -> str:
    """Clean and normalize an extracted entity name."""
    # Remove trailing/leading whitespace and common artifacts
    name = name.strip()
    # Remove trailing punctuation
    name = re.sub(r"[.,;:!?]+$", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name)
    return name


def _extract_activities(text: str) -> list[ExtractedEntity]:
    """Extract activity entities from text using pattern matching."""
    entities: list[ExtractedEntity] = []
    seen_names: set[str] = set()

    for pattern in _ACTIVITY_PATTERNS:
        for match in pattern.finditer(text):
            # Combine verb + object
            if match.lastindex and match.lastindex >= 2:
                verb = match.group(1).strip()
                obj = match.group(2).strip()
                name = _clean_entity_name(f"{verb} {obj}")
            else:
                name = _clean_entity_name(match.group(0))

            name_lower = name.lower()
            if name_lower in seen_names or len(name) < 5:
                continue
            seen_names.add(name_lower)

            entity_id = _generate_entity_id("activity", name)
            entities.append(
                ExtractedEntity(
                    id=entity_id,
                    entity_type=EntityType.ACTIVITY,
                    name=name,
                    confidence=0.7,
                    source_span=match.group(0),
                )
            )

    return entities


def _extract_roles(text: str) -> list[ExtractedEntity]:
    """Extract role entities from text using pattern matching."""
    entities: list[ExtractedEntity] = []
    seen_names: set[str] = set()

    for pattern in _ROLE_PATTERNS:
        for match in pattern.finditer(text):
            name = _clean_entity_name(match.group(1) if match.lastindex else match.group(0))
            name_lower = name.lower()

            if name_lower in seen_names or len(name) < 3:
                continue
            seen_names.add(name_lower)

            # Higher confidence for explicit title patterns (first pattern)
            confidence = 0.8 if match.group(0)[0].isupper() else 0.6

            entity_id = _generate_entity_id("role", name)
            entities.append(
                ExtractedEntity(
                    id=entity_id,
                    entity_type=EntityType.ROLE,
                    name=name,
                    confidence=confidence,
                    source_span=match.group(0),
                )
            )

    return entities


def _extract_systems(text: str) -> list[ExtractedEntity]:
    """Extract system entities from text using pattern matching."""
    entities: list[ExtractedEntity] = []
    seen_names: set[str] = set()

    for pattern in _SYSTEM_PATTERNS:
        for match in pattern.finditer(text):
            if match.lastindex and match.lastindex >= 1:
                name = _clean_entity_name(match.group(1))
            else:
                name = _clean_entity_name(match.group(0))

            name_lower = name.lower()
            if name_lower in seen_names or len(name) < 2:
                continue
            seen_names.add(name_lower)

            # Known systems get higher confidence
            known_systems = {
                "sap",
                "oracle",
                "salesforce",
                "workday",
                "servicenow",
                "jira",
                "confluence",
                "sharepoint",
                "teams",
                "slack",
                "tableau",
                "power bi",
                "powerbi",
                "snowflake",
                "aws",
                "azure",
                "gcp",
                "kubernetes",
                "jenkins",
                "github",
                "gitlab",
            }
            confidence = 0.9 if name_lower in known_systems else 0.7

            entity_id = _generate_entity_id("system", name)
            entities.append(
                ExtractedEntity(
                    id=entity_id,
                    entity_type=EntityType.SYSTEM,
                    name=name,
                    confidence=confidence,
                    source_span=match.group(0),
                )
            )

    return entities


def _extract_decisions(text: str) -> list[ExtractedEntity]:
    """Extract decision entities from text using pattern matching."""
    entities: list[ExtractedEntity] = []
    seen_names: set[str] = set()

    for pattern in _DECISION_PATTERNS:
        for match in pattern.finditer(text):
            # For conditional patterns, use the full match as the decision
            if match.lastindex and match.lastindex >= 2:
                condition = _clean_entity_name(match.group(2))
                keyword = match.group(1).strip()
                name = f"{keyword} {condition}"
            elif match.lastindex and match.lastindex >= 1:
                name = _clean_entity_name(match.group(1))
            else:
                name = _clean_entity_name(match.group(0))

            name_lower = name.lower()
            if name_lower in seen_names or len(name) < 8:
                continue
            seen_names.add(name_lower)

            entity_id = _generate_entity_id("decision", name)
            entities.append(
                ExtractedEntity(
                    id=entity_id,
                    entity_type=EntityType.DECISION,
                    name=name,
                    confidence=0.6,
                    source_span=match.group(0),
                )
            )

    return entities


def _extract_documents(text: str) -> list[ExtractedEntity]:
    """Extract document entities from text using pattern matching."""
    entities: list[ExtractedEntity] = []
    seen_names: set[str] = set()

    for pattern in _DOCUMENT_PATTERNS:
        for match in pattern.finditer(text):
            name = _clean_entity_name(match.group(1) if match.lastindex else match.group(0))
            name_lower = name.lower()

            if name_lower in seen_names or len(name) < 3:
                continue
            seen_names.add(name_lower)

            entity_id = _generate_entity_id("document", name)
            entities.append(
                ExtractedEntity(
                    id=entity_id,
                    entity_type=EntityType.DOCUMENT,
                    name=name,
                    confidence=0.8,
                    source_span=match.group(0),
                )
            )

    return entities


SEED_TERM_CONFIDENCE_BOOST: float = 0.15
"""Confidence boost for entities that match an engagement seed term."""


async def extract_entities(
    text: str,
    fragment_id: str | None = None,
    use_llm: bool = False,
    seed_terms: list[str] | None = None,
) -> ExtractionResult:
    """Extract entities from a text fragment.

    Uses rule-based NLP patterns as the MVP fallback. When use_llm is True,
    an LLM-based extraction path (not yet implemented) would be used.

    If seed_terms are provided, entities whose names match a seed term
    receive a confidence boost of SEED_TERM_CONFIDENCE_BOOST.

    Args:
        text: The text to extract entities from.
        fragment_id: Optional ID of the source fragment.
        use_llm: Whether to use LLM-based extraction (not yet implemented).
        seed_terms: Canonical terms from the engagement seed list.

    Returns:
        ExtractionResult with all extracted entities.
    """
    if not text or not text.strip():
        return ExtractionResult(
            entities=[],
            fragment_id=fragment_id,
            raw_text_length=0,
        )

    # Rule-based extraction (MVP)
    all_entities: list[ExtractedEntity] = []
    all_entities.extend(_extract_activities(text))
    all_entities.extend(_extract_roles(text))
    all_entities.extend(_extract_systems(text))
    all_entities.extend(_extract_decisions(text))
    all_entities.extend(_extract_documents(text))

    # Apply seed term confidence boost
    if seed_terms:
        seed_lower = {t.lower().strip() for t in seed_terms}
        for entity in all_entities:
            matched_seed = _match_seed_term(entity.name, seed_lower)
            if matched_seed:
                entity.confidence = min(1.0, entity.confidence + SEED_TERM_CONFIDENCE_BOOST)
                entity.metadata["matched_seed_term"] = matched_seed

    return ExtractionResult(
        entities=all_entities,
        fragment_id=fragment_id,
        raw_text_length=len(text),
    )


def _match_seed_term(entity_name: str, seed_terms_lower: set[str]) -> str | None:
    """Check if an entity name matches a seed term (case-insensitive).

    Returns the matched seed term or None.
    """
    name_lower = entity_name.lower().strip()
    if name_lower in seed_terms_lower:
        return name_lower
    # Also check substring containment for compound names
    # Require minimum seed length of 3 to avoid false positives on short terms
    for seed in seed_terms_lower:
        if len(seed) >= 3 and (seed in name_lower or name_lower in seed):
            return seed
    return None


def _normalize_name(name: str) -> str:
    """Normalize a name for comparison during entity resolution."""
    # Lowercase, strip, collapse whitespace
    normalized = name.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    # Remove common articles/prepositions for fuzzy matching
    normalized = re.sub(r"\b(the|a|an|of|for|in|on|to|by|with)\b", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def resolve_entities(
    entities: list[ExtractedEntity],
) -> tuple[list[ExtractedEntity], list[DuplicateCandidate]]:
    """Resolve entities by merging duplicates and near-duplicates.

    Uses normalized name comparison to detect when different names refer
    to the same entity. The entity with the highest confidence is kept
    as the canonical entry; others become aliases.

    Also detects potential duplicate pairs across entities of the same type
    that share significant normalized name overlap (containment check).

    Args:
        entities: List of entities to resolve.

    Returns:
        Tuple of (resolved entities, duplicate candidate pairs).
    """
    if not entities:
        return [], []

    # Group by (entity_type, normalized_name)
    groups: dict[tuple[str, str], list[ExtractedEntity]] = {}
    for entity in entities:
        key = (entity.entity_type, _normalize_name(entity.name))
        if key not in groups:
            groups[key] = []
        groups[key].append(entity)

    resolved: list[ExtractedEntity] = []
    for group in groups.values():
        if len(group) == 1:
            resolved.append(group[0])
        else:
            # Keep the highest-confidence entity as canonical
            group.sort(key=lambda e: e.confidence, reverse=True)
            canonical = group[0]
            # Collect aliases from the rest
            for other in group[1:]:
                if other.name != canonical.name and other.name not in canonical.aliases:
                    canonical.aliases.append(other.name)
            resolved.append(canonical)

    # Detect cross-entity duplicate candidates (different raw names, same type)
    duplicate_candidates = _detect_duplicate_candidates(resolved)

    return resolved, duplicate_candidates


def _detect_duplicate_candidates(
    entities: list[ExtractedEntity],
) -> list[DuplicateCandidate]:
    """Detect potential duplicate pairs among resolved entities.

    Compares entities of the same type that have different canonical names
    but high normalized name overlap (one contains the other, or they share
    a significant common prefix).

    Args:
        entities: List of resolved entities.

    Returns:
        List of duplicate candidate pairs.
    """
    candidates: list[DuplicateCandidate] = []
    seen_pairs: set[tuple[str, str]] = set()

    # Group by entity type
    by_type: dict[str, list[ExtractedEntity]] = {}
    for entity in entities:
        if entity.entity_type not in by_type:
            by_type[entity.entity_type] = []
        by_type[entity.entity_type].append(entity)

    for etype, type_entities in by_type.items():
        for i, a in enumerate(type_entities):
            for b in type_entities[i + 1 :]:
                norm_a = _normalize_name(a.name)
                norm_b = _normalize_name(b.name)

                if norm_a == norm_b:
                    continue  # Already merged during resolution

                pair_key = (min(a.id, b.id), max(a.id, b.id))
                if pair_key in seen_pairs:
                    continue

                reason = _check_name_similarity(norm_a, norm_b)
                if reason:
                    seen_pairs.add(pair_key)
                    candidates.append(
                        DuplicateCandidate(
                            entity_a_id=a.id,
                            entity_b_id=b.id,
                            entity_a_name=a.name,
                            entity_b_name=b.name,
                            entity_type=EntityType(etype),
                            similarity_reason=reason,
                        )
                    )

    return candidates


def _check_name_similarity(norm_a: str, norm_b: str) -> str | None:
    """Check if two normalized names are similar enough to be duplicates.

    Checks containment, acronym matching, and high word overlap.

    Returns a reason string if similar, None otherwise.
    """
    # Containment: one name contains the other
    if norm_a in norm_b:
        return f"'{norm_a}' is contained in '{norm_b}'"
    if norm_b in norm_a:
        return f"'{norm_b}' is contained in '{norm_a}'"

    words_a = set(norm_a.split())
    words_b = set(norm_b.split())

    # Abbreviation/acronym detection: check if initials of one match the other
    words_a_list = norm_a.split()
    words_b_list = norm_b.split()
    if len(words_a_list) >= 2 and len(words_b_list) == 1:
        initials = "".join(w[0] for w in words_a_list if w)
        if initials == norm_b:
            return f"'{norm_b}' is an acronym of '{norm_a}'"
    if len(words_b_list) >= 2 and len(words_a_list) == 1:
        initials = "".join(w[0] for w in words_b_list if w)
        if initials == norm_a:
            return f"'{norm_a}' is an acronym of '{norm_b}'"

    # High word overlap: >50% of the smaller set's words shared
    # Require smaller >= 2 to avoid false positives on single-word entities
    if words_a and words_b:
        overlap = words_a & words_b
        smaller = min(len(words_a), len(words_b))
        if smaller >= 2 and len(overlap) / smaller >= 0.5:
            return f"High word overlap: {overlap}"

    return None
