/**
 * Deterministic seed data IDs for E2E tests.
 *
 * These UUIDs are computed with uuid5(NS, name) using the same namespace
 * as scripts/seed_demo.py so they match the seeded database exactly.
 *
 * Namespace: a1b2c3d4-e5f6-7890-abcd-ef1234567890
 */

// ── Core IDs ────────────────────────────────────────────────────────

export const ENGAGEMENT_ID = "1db9aa11-c73b-5867-82a3-864dd695cf23";
export const TOM_ID = "1454a7ab-2f76-57cc-bc27-ac1d7adbdf7e";
export const PROCESS_MODEL_ID = "b0e82fc6-49db-58a4-9a1a-01203163c60f";
export const BASELINE_ID = "32b20eb5-966a-522f-b6fb-b6e98419294f";

// ── Users ───────────────────────────────────────────────────────────

export const USERS = {
  admin: {
    id: "b8191819-5e28-5323-aa6a-fc636e42aeaa",
    email: "admin@acme-demo.com",
    password: "demo",
    name: "Sarah Chen",
    role: "platform_admin",
  },
  lead: {
    id: "55cafb59-81b4-5c28-9b17-f5789fa3bc4e",
    email: "lead@acme-demo.com",
    password: "demo",
    name: "Marcus Johnson",
    role: "engagement_lead",
  },
  analyst: {
    id: "0ea90c06-cc86-503c-ab77-8a081aa134e1",
    email: "analyst@acme-demo.com",
    password: "demo",
    name: "Priya Patel",
    role: "process_analyst",
  },
  viewer: {
    id: "0ddb75a0-a43d-5f6e-95cb-ddc254551c52",
    email: "viewer@acme-demo.com",
    password: "demo",
    name: "David Kim",
    role: "client_viewer",
  },
} as const;

// ── Evidence IDs ────────────────────────────────────────────────────

export const EVIDENCE_IDS = {
  "loan-policy": "e95612e6-8949-5bea-8534-b62fd6ca388c",
  "process-doc": "c358fee8-f024-5c2a-9a9d-cff7036247ce",
  "interview-ops-mgr": "26a054fc-7471-5652-bcc2-56e524b736e0",
  "interview-cro": "de8db4bc-2c82-524e-8cc2-d3394c0871f7",
  "bpmn-as-is": "5fd3d287-6dda-5e9b-aad0-1fb84a209cf4",
  "signavio-export": "fbea2c77-2985-55b3-9a19-ba60c8942758",
  "screen-recording": "e36a63ba-4974-5209-9d38-9a2b0d4bb9be",
  "compliance-report": "0bd2a861-c325-59b1-a7ff-9b452c83f350",
  "audit-controls": "3f6c6a26-ae9c-56ab-a4e1-16cf42711b29",
  "email-thread": "52968ef5-f338-507a-bee0-fb5aadfe6c03",
  "training-guide": "36ead8e1-a5a8-5cbe-82b2-ad259cf76756",
  "data-extract": "0a673ff2-0422-5e77-9d3c-2d3950e4cbe3",
  "task-mining-obs-1": "b6ad441a-ff65-5fea-8ddf-fffc3bd54338",
  "task-mining-obs-2": "96cab1d7-a9f0-50d5-8ad5-96e06e11ae4b",
  "task-mining-obs-3": "75e8c6b7-8d8f-5269-a3c4-939b198ebbfc",
} as const;

// ── Monitoring IDs ──────────────────────────────────────────────────

export const MONITORING_JOB_IDS = [
  "1cff1fbb-bc80-59fd-90b5-fdfcca3e647c",
  "d84239ef-b079-5458-aa5d-13f940d57cdd",
] as const;

export const SCENARIO_IDS = [
  "15fbe069-f7bd-5161-8b68-7b0b72dbacca",
  "17430837-573b-5a3f-a8c3-13e6f4c2a0be",
  "92c217a5-eca9-5fc1-a581-20024caf73c5",
] as const;

// ── WGI Feature IDs ────────────────────────────────────────────────

export const SWITCHING_TRACE_IDS = [
  "460e7138-9e07-535b-b276-6fd2943d78b7",
  "6ecd11eb-12a8-5deb-a747-3c65c2cddfbc",
  "d4291e13-a816-5ca1-b895-04f6062892b9",
] as const;

export const TRANSITION_MATRIX_ID = "60aae798-0db6-5804-9a92-3dabe36a1b85";

export const VCE_IDS = [
  "cf4adadd-101e-55ac-9851-38e967279a09",
  "58bbd73f-8bef-5aed-b4ca-6eb0e7c9b410",
  "e329e9f2-7ef0-571f-bcda-2ee9192f73b0",
  "086fb074-3877-51fd-99e1-39e88f8c4d9b",
  "9178e3bb-28c9-5ee7-ab74-b2e6062ce8f7",
] as const;

export const CASE_LINK_IDS = [
  "3527cf80-6ab8-5117-b243-d0aa3a72574f",
  "892f4238-d5d1-5c19-9be5-8f94d1524f79",
  "43eefcf1-a2a4-5792-b9fc-6353a60c5132",
  "fc777d38-5b53-5ffb-aaf6-1f88dedd603c",
] as const;

// ── Engagement metadata ─────────────────────────────────────────────

export const ENGAGEMENT = {
  name: "Acme Corp — Loan Origination Transformation",
  client: "Acme Financial Services",
  businessArea: "Retail Lending",
} as const;
