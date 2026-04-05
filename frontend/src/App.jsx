import { useEffect, useState } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000";

const isDistressedProperty = (deal) => {
  const owner1 = (deal.owners_name_1 || "").toLowerCase();
  const owner2 = (deal.owners_name_2 || "").toLowerCase();

  return (
    owner1.includes("llc") ||
    owner1.includes("secretary") ||
    owner1.includes("bank") ||
    owner2.includes("llc") ||
    owner2.includes("secretary") ||
    owner2.includes("bank")
  );
};

export default function App() {
  const [deals, setDeals] = useState([]);
  const [muni, setMuni] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [showDistressedOnly, setShowDistressedOnly] = useState(false);

  const fetchDeals = () => {
    setLoading(true);

    axios
      .get(`${API}/deals`, {
        params: {
          muni: muni || undefined,
          min_score: minScore || 0,
          limit: 50,
        },
      })
      .then((res) => {
        setDeals(res.data.results || []);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  const searchDeals = (q) => {
    const query = (q || "").trim();
    if (!query) return fetchDeals();

    setLoading(true);

    axios
      .get(`${API}/search`, {
        params: { q: query },
      })
      .then((res) => {
        setDeals(res.data.results || []);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchDeals();
  }, []);

  const visibleDeals = showDistressedOnly
    ? deals.filter(isDistressedProperty)
    : deals;

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h1>🏡 Real Estate Deal Dashboard</h1>

      <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
        <input
          placeholder="Search address..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && searchDeals(search)}
        />
        <button onClick={() => searchDeals(search)}>Search</button>

        <input
          placeholder="Filter municipality"
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
        <button onClick={() => setShowDistressedOnly((prev) => !prev)}>
          {showDistressedOnly ? "Show All Properties" : "Show Distressed Only"}
        </button>
      </div>

      {loading && <p>Loading deals...</p>}

      <table width="100%" border="1" cellPadding="8">
        <thead>
          <tr>
            <th>Parcel ID</th>
            <th>Address</th>
            <th>Owner Hidden Name</th>
            <th>Owner 1</th>
            <th>Owner 2</th>
            <th>Muni</th>
            <th>Total Assessed Value</th>
            <th>Deal Score</th>
            <th>Sale Type</th>
            <th>Status</th>
          </tr>
        </thead>

        <tbody>
          {visibleDeals.map((d) => {
            const score = d.deal_score ?? 0;
            const totalAssessedValue =
              d.total_assessed_value ?? d.assessed_value ?? null;

            const isDistressed = isDistressedProperty(d);

            return (
              <tr
                key={d.parcel_id}
                style={{ backgroundColor: isDistressed ? "#ffe6e6" : "white" }}
              >
                <td>{d.parcel_id}</td>
                <td>{d.address}</td>
                <td>{d.owners_hidename || "—"}</td>
                <td>{d.owners_name_1 || "—"}</td>
                <td>{d.owners_name_2 || "—"}</td>
                <td>{d.muni}</td>
                <td>
                  {totalAssessedValue != null
                    ? `$${totalAssessedValue.toLocaleString()}`
                    : "—"}
                </td>
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
