import { useEffect, useState } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000";

export default function App() {
  const [deals, setDeals] = useState([]);
  const [muni, setMuni] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  // -------------------------
  // Fetch main deals feed
  // -------------------------
  const fetchDeals = async () => {
    setLoading(true);

    try {
      const res = await axios.get(`${API}/deals`, {
        params: {
          muni: muni || undefined,
          min_score: minScore || 0,
          limit: 50,
        },
      });

      setDeals(res.data.results || []);
    } finally {
      setLoading(false);
    }
  };

  // -------------------------
  // Search endpoint
  // -------------------------
  const searchDeals = async (q) => {
    if (!q) return fetchDeals();

    setLoading(true);

    try {
      const res = await axios.get(`${API}/search`, {
        params: { q },
      });

      setDeals(res.data.results || []);
    } finally {
      setLoading(false);
    }
  };

  // -------------------------
  // Initial load
  // -------------------------
  useEffect(() => {
    fetchDeals();
  }, []);

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h1>🏡 Real Estate Deal Dashboard</h1>

      {/* -------------------------
          Filters
      -------------------------- */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
        <input
          placeholder="Search address..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && searchDeals(search)}
        />

        <input
          placeholder="Muni"
          value={muni}
          onChange={(e) => setMuni(e.target.value)}
        />

        <input
          type="number"
          placeholder="Min Score"
          value={minScore}
          onChange={(e) => setMinScore(Number(e.target.value))}
        />

        <button onClick={fetchDeals}>Apply Filters</button>
      </div>

      {/* -------------------------
          Loading state
      -------------------------- */}
      {loading && <p>Loading deals...</p>}

      {/* -------------------------
          Table
      -------------------------- */}
      <table width="100%" border="1" cellPadding="8">
        <thead>
          <tr>
            <th>Parcel ID</th>
            <th>Address</th>
            <th>Muni</th>
            <th>Assessed Value</th>
            <th>Deal Score</th>
            <th>Sale Type</th>
            <th>Status</th>
          </tr>
        </thead>

        <tbody>
          {deals.map((d) => {
            const saleType = (d.sale_type || "").toLowerCase();
            const score = d.deal_score ?? 0;

            // -------------------------
            // improved distress logic
            // -------------------------
            const isDistressed =
              saleType.includes("foreclosure") ||
              saleType.includes("reo") ||
              saleType.includes("bank") ||
              saleType.includes("lien") ||
              score >= 2.0; // matches log-based scoring better

            return (
              <tr
                key={d.parcel_id}
                style={{
                  backgroundColor: isDistressed ? "#ffe6e6" : "white",
                }}
              >
                <td>{d.parcel_id}</td>
                <td>{d.address}</td>
                <td>{d.muni}</td>
                <td>${d.assessed_value?.toLocaleString()}</td>

                <td>
                  <b>{score.toFixed(2)}</b>
                </td>

                <td>{d.sale_type || "—"}</td>

                <td>{isDistressed ? "🔥 Distressed" : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
