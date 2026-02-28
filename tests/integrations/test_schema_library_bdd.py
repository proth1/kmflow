"""BDD tests for the schema intelligence library (Story #335).

Tests schema template loading, lifecycle mapping, and manual fallback.
"""

from __future__ import annotations

from src.integrations.schema_library.loader import SchemaLibrary


class TestServiceNowLifecycleAutoMapping:
    """Scenario 1: ServiceNow lifecycle auto-mapping from schema template."""

    def test_incident_lifecycle_states_mapped(self) -> None:
        """Incident lifecycle states are automatically mapped."""
        library = SchemaLibrary()
        template = library.get_template("servicenow")
        assert template is not None

        incident = template.get_table("incident")
        assert incident is not None
        assert incident.lifecycle_states["1"] == "new"
        assert incident.lifecycle_states["2"] == "in_progress"
        assert incident.lifecycle_states["6"] == "resolved"
        assert incident.lifecycle_states["7"] == "closed"

    def test_incident_fields_mapped(self) -> None:
        """Standard incident fields are pre-mapped."""
        library = SchemaLibrary()
        template = library.get_template("servicenow")
        assert template is not None

        incident = template.get_table("incident")
        assert incident is not None

        field_map = {f.source_field: f.kmflow_attribute for f in incident.fields}
        assert field_map["number"] == "case_id"
        assert field_map["short_description"] == "title"
        assert field_map["state"] == "lifecycle_phase"
        assert field_map["assigned_to"] == "assignee"

    def test_incident_correlation_keys(self) -> None:
        """Incident correlation keys are defined."""
        library = SchemaLibrary()
        template = library.get_template("servicenow")
        assert template is not None

        incident = template.get_table("incident")
        assert incident is not None
        assert "number" in incident.correlation_keys
        assert "sys_id" in incident.correlation_keys

    def test_change_request_table_exists(self) -> None:
        """Change request table template is available."""
        library = SchemaLibrary()
        template = library.get_template("servicenow")
        assert template is not None

        change = template.get_table("change_request")
        assert change is not None
        assert len(change.lifecycle_states) > 0
        assert len(change.fields) > 0

    def test_problem_table_exists(self) -> None:
        """Problem table template is available."""
        library = SchemaLibrary()
        template = library.get_template("servicenow")
        assert template is not None

        problem = template.get_table("problem")
        assert problem is not None
        assert len(problem.lifecycle_states) > 0


class TestSAPSchemaTemplate:
    """Scenario 2: SAP schema template pre-populates field mappings."""

    def test_bkpf_table_fields(self) -> None:
        """BKPF (Accounting Document Header) fields are pre-populated."""
        library = SchemaLibrary()
        template = library.get_template("sap")
        assert template is not None

        bkpf = template.get_table("BKPF")
        assert bkpf is not None

        field_map = {f.source_field: f.kmflow_attribute for f in bkpf.fields}
        assert field_map["BELNR"] == "document_number"
        assert field_map["BUKRS"] == "company_code"
        assert field_map["BUDAT"] == "posting_date"

    def test_bseg_table_fields(self) -> None:
        """BSEG (Line Item) fields are pre-populated."""
        library = SchemaLibrary()
        template = library.get_template("sap")
        assert template is not None

        bseg = template.get_table("BSEG")
        assert bseg is not None

        field_map = {f.source_field: f.kmflow_attribute for f in bseg.fields}
        assert field_map["HKONT"] == "gl_account"
        assert field_map["LIFNR"] == "vendor_number"
        assert field_map["DMBTR"] == "amount_local"

    def test_bkpf_correlation_keys(self) -> None:
        """BKPF correlation keys include company code, doc number, and fiscal year."""
        library = SchemaLibrary()
        template = library.get_template("sap")
        assert template is not None

        bkpf = template.get_table("BKPF")
        assert bkpf is not None
        assert "BUKRS" in bkpf.correlation_keys
        assert "BELNR" in bkpf.correlation_keys
        assert "GJAHR" in bkpf.correlation_keys

    def test_vbak_sales_document(self) -> None:
        """VBAK (Sales Document Header) is available for SD module."""
        library = SchemaLibrary()
        template = library.get_template("sap")
        assert template is not None

        vbak = template.get_table("VBAK")
        assert vbak is not None
        assert len(vbak.fields) > 0
        assert "VBELN" in vbak.correlation_keys

    def test_sap_lifecycle_states(self) -> None:
        """BKPF lifecycle states map document status codes."""
        library = SchemaLibrary()
        template = library.get_template("sap")
        assert template is not None

        bkpf = template.get_table("BKPF")
        assert bkpf is not None
        assert bkpf.lifecycle_states["V"] == "posted"
        assert bkpf.lifecycle_states["D"] == "reversed"


class TestManualMappingFallback:
    """Scenario 3: Manual schema mapping fallback for unlisted platforms."""

    def test_unknown_platform_returns_none(self) -> None:
        """Unknown platform returns None signaling manual mapping."""
        library = SchemaLibrary()
        result = library.get_template("oracle_erp")
        assert result is None

    def test_has_template_false_for_unknown(self) -> None:
        """has_template returns False for unknown platform."""
        library = SchemaLibrary()
        assert library.has_template("oracle_erp") is False

    def test_has_template_true_for_known(self) -> None:
        """has_template returns True for known platforms."""
        library = SchemaLibrary()
        assert library.has_template("servicenow") is True
        assert library.has_template("sap") is True
        assert library.has_template("salesforce") is True

    def test_case_insensitive_lookup(self) -> None:
        """Platform names are case-insensitive."""
        library = SchemaLibrary()
        assert library.get_template("ServiceNow") is not None
        assert library.get_template("SALESFORCE") is not None
        assert library.get_template("SAP") is not None


class TestSalesforceSchemaTemplate:
    """Salesforce schema template covers Opportunity and Case objects."""

    def test_opportunity_fields(self) -> None:
        library = SchemaLibrary()
        template = library.get_template("salesforce")
        assert template is not None

        opp = template.get_table("Opportunity")
        assert opp is not None

        field_map = {f.source_field: f.kmflow_attribute for f in opp.fields}
        assert field_map["StageName"] == "lifecycle_phase"
        assert field_map["Amount"] == "amount"
        assert field_map["OwnerId"] == "assignee"

    def test_opportunity_lifecycle_states(self) -> None:
        library = SchemaLibrary()
        template = library.get_template("salesforce")
        assert template is not None

        opp = template.get_table("Opportunity")
        assert opp is not None
        assert opp.lifecycle_states["Closed Won"] == "closed_won"
        assert opp.lifecycle_states["Closed Lost"] == "closed_lost"
        assert opp.lifecycle_states["Prospecting"] == "prospecting"

    def test_case_object(self) -> None:
        library = SchemaLibrary()
        template = library.get_template("salesforce")
        assert template is not None

        case = template.get_table("Case")
        assert case is not None
        assert len(case.fields) > 0
        assert case.lifecycle_states["New"] == "new"
        assert case.lifecycle_states["Closed"] == "closed"


class TestSchemaLibrary:
    """General library functionality."""

    def test_list_platforms(self) -> None:
        library = SchemaLibrary()
        platforms = library.list_platforms()
        assert "salesforce" in platforms
        assert "sap" in platforms
        assert "servicenow" in platforms

    def test_template_to_dict(self) -> None:
        library = SchemaLibrary()
        template = library.get_template("servicenow")
        assert template is not None

        d = template.to_dict()
        assert d["platform"] == "servicenow"
        assert d["version"] == "1.0"
        assert len(d["tables"]) == 3

    def test_table_to_dict(self) -> None:
        library = SchemaLibrary()
        template = library.get_template("servicenow")
        assert template is not None

        incident = template.get_table("incident")
        assert incident is not None

        d = incident.to_dict()
        assert d["name"] == "incident"
        assert len(d["fields"]) > 0
        assert len(d["lifecycle_states"]) > 0
        assert len(d["correlation_keys"]) > 0

    def test_field_mapping_to_dict(self) -> None:
        library = SchemaLibrary()
        template = library.get_template("sap")
        assert template is not None

        bkpf = template.get_table("BKPF")
        assert bkpf is not None

        field_dict = bkpf.fields[0].to_dict()
        assert "source_field" in field_dict
        assert "kmflow_attribute" in field_dict
        assert "transform_fn" in field_dict

    def test_get_table_case_insensitive(self) -> None:
        library = SchemaLibrary()
        template = library.get_template("servicenow")
        assert template is not None

        assert template.get_table("INCIDENT") is not None
        assert template.get_table("Incident") is not None

    def test_get_table_returns_none_for_unknown(self) -> None:
        library = SchemaLibrary()
        template = library.get_template("servicenow")
        assert template is not None

        assert template.get_table("nonexistent") is None
