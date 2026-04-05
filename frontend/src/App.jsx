import { useEffect, useState } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000";

const hasBankWord = (ownerName) => /\bbank\b/.test(ownerName);

const isDistressedProperty = (deal) => {
  const owner1 = (deal.owners_name_1 || "").toLowerCase();
  const owner2 = (deal.owners_name_2 || "").toLowerCase();

  return (
    owner1.includes("secretary") ||
    hasBankWord(owner1) ||
    owner2.includes("secretary") ||
    hasBankWord(owner2)
  );
};

const DealsTable = ({ deals }) => (
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
      {deals.map((d) => {
        const score = d.deal_score ?? 0;
        const totalAssessedValue = d.total_assessed_value ?? d.assessed_value ?? null;
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
);

export default function App() {
  const [deals, setDeals] = useState([]);
  const [muni, setMuni] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [showDistressedOnly, setShowDistressedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 50,
    total: 0,
    total_pages: 1,
  });
  const [isSearchMode, setIsSearchMode] = useState(false);

  const fetchDeals = ({ distressedOnly = false, pageNumber = 1 } = {}) => {
    setLoading(true);
    setIsSearchMode(false);

    axios
      .get(`${API}/deals`, {
        params: {
          muni: muni || undefined,
          min_score: minScore || 0,
          distressed_only: distressedOnly || undefined,
          limit: 50,
          page: pageNumber,
        },
      })
      .then((res) => {
        const results = res.data.results || [];
        const nextPagination = res.data.pagination || {
          page: pageNumber,
          limit: 50,
          total: results.length,
          total_pages: 1,
        };
        setDeals(distressedOnly ? results.filter(isDistressedProperty) : results);
        setPagination(nextPagination);
        setPage(nextPagination.page);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  const searchDeals = (q) => {
    const query = (q || "").trim();
    if (!query) {
      return fetchDeals({ distressedOnly: showDistressedOnly, pageNumber: 1 });
    }

    setLoading(true);
    setIsSearchMode(true);

    axios
      .get(`${API}/search`, {
        params: { q: query, limit: 50 },
      })
      .then((res) => {
        const results = res.data.results || [];
        setDeals(showDistressedOnly ? results.filter(isDistressedProperty) : results);
        setPagination({
          page: 1,
          limit: 50,
          total: results.length,
          total_pages: 1,
        });
        setPage(1);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchDeals();
  }, []);

  const applyFilters = () => {
    fetchDeals({ distressedOnly: showDistressedOnly, pageNumber: 1 });
  };

  const goToNextPage = () => {
    if (isSearchMode || page >= pagination.total_pages) return;
    fetchDeals({ distressedOnly: showDistressedOnly, pageNumber: page + 1 });
  };

  const goToPreviousPage = () => {
    if (isSearchMode || page <= 1) return;
    fetchDeals({ distressedOnly: showDistressedOnly, pageNumber: page - 1 });
  };

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h1>🏡 Real Estate Results Dashboard</h1>

      <div style={{ display: "flex", gap: 10, marginBottom: 20, alignItems: "center" }}>
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

        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input
            type="checkbox"
            checked={showDistressedOnly}
            onChange={(e) => setShowDistressedOnly(e.target.checked)}
          />
          Distressed properties only
        </label>

        <button onClick={applyFilters}>Apply Filters</button>
      </div>

      {loading && <p>Loading results...</p>}
      <p>
        Showing page {pagination.page} of {Math.max(pagination.total_pages, 1)} (
        {pagination.total.toLocaleString()} total results)
      </p>
      {!isSearchMode && (
        <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
          <button onClick={goToPreviousPage} disabled={page <= 1}>
            ← Previous
          </button>
          <button
            onClick={goToNextPage}
            disabled={page >= pagination.total_pages}
          >
            Next →
          </button>
        </div>
      )}
      <DealsTable deals={deals} />
    </div>
  );
}
