import HealthStatus from "@/components/HealthStatus";

/**
 * KMFlow landing page.
 *
 * Shows the platform name, description, and backend health status.
 */
export default function HomePage() {
  return (
    <main
      style={{
        maxWidth: "960px",
        margin: "0 auto",
        padding: "48px 24px",
      }}
    >
      <header style={{ marginBottom: "48px" }}>
        <h1
          style={{
            fontSize: "36px",
            fontWeight: 700,
            marginBottom: "8px",
          }}
        >
          KMFlow
        </h1>
        <p
          style={{
            fontSize: "18px",
            color: "#6b7280",
            marginTop: 0,
          }}
        >
          AI-powered Process Intelligence Platform
        </p>
      </header>

      <section
        style={{
          backgroundColor: "#ffffff",
          border: "1px solid #e5e7eb",
          borderRadius: "12px",
          padding: "24px",
          marginBottom: "32px",
        }}
      >
        <h2 style={{ fontSize: "20px", marginTop: 0 }}>Platform Status</h2>
        <HealthStatus />
      </section>

      <section
        style={{
          backgroundColor: "#ffffff",
          border: "1px solid #e5e7eb",
          borderRadius: "12px",
          padding: "24px",
        }}
      >
        <h2 style={{ fontSize: "20px", marginTop: 0 }}>About</h2>
        <p style={{ lineHeight: 1.6 }}>
          KMFlow transforms consulting delivery by enabling data-driven process
          conversations from day one of client engagement. It ingests diverse
          client evidence, builds semantic relationships, synthesizes
          confidence-scored process views, and automates TOM gap analysis.
        </p>
        <ul style={{ lineHeight: 1.8 }}>
          <li>Evidence-first approach across 12 evidence categories</li>
          <li>Semantic knowledge graph with Neo4j</li>
          <li>Confidence-scored process model generation (LCD algorithm)</li>
          <li>Automated Target Operating Model gap analysis</li>
          <li>
            Regulatory, policy, and control overlay as connective tissue
          </li>
        </ul>
      </section>
    </main>
  );
}
