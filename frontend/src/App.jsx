import { useEffect, useState } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000";

const hasBankWord = (ownerName) => /\bbank\b/.test(ownerName);


const MUNICIPALITIES = {
  "01": "Allen Township",
  "02": "Bangor Borough",
  "03": "Bath Borough",
  "04": "Bethlehem City",
  "05": "Bethlehem Township",
  "06": "Bushkill Township",
  "07": "Chapman Borough",
  "08": "East Allen Township",
  "09": "East Bangor Borough",
  "10": "Easton City",
  "11": "Forks Township",
  "12": "Freemansburgh Borough",
  "13": "Glendon Borough",
  "14": "Hanover Township",
  "15": "Hellertown Borough",
  "16": "Lehigh Township",
  "17": "Lower Mount Bethel Township",
  "18": "Lower Nazareth Township",
  "19": "Lower Saucon Township",
  "20": "Moore Township",
  "21": "Nazareth Borough",
  "22": "Northampton Borough",
  "23": "North Catasaqua Borough",
  "24": "Palmer Township",
  "25": "Pen Argyl Borough",
  "26": "Plainfield Township",
  "27": "Portland Borough",
  "28": "Roseto Borough",
  "29": "Stockerton Borough",
  "30": "Tatamy Borough",
  "31": "Upper Mount Bethel Township",
  "32": "Upper Nazareth Township",
  "33": "Walnutport Borough",
  "34": "Washington Township",
  "35": "West Easton Borough",
  "36": "Williams Township",
  "37": "Wilson Borough",
  "38": "Wind Gap Borough",
};

const formatMuni = (muniCode) => {
  const raw = String(muniCode || "").trim();
  if (!raw) return "—";

  const normalized = /^\d+$/.test(raw) ? raw.padStart(2, "0") : raw;
  const label = MUNICIPALITIES[normalized];

  return label || raw;
};

const isDistressedProperty = (deal) => {
  const owner1 = (deal.owners_name_1 || "").toLowerCase();
  const owner2 = (deal.owners_name_2 || "").toLowerCase();
  const isBankOwned = hasBankWord(owner1) || hasBankWord(owner2);

  return !isBankOwned && (owner1.includes("secretary") || owner2.includes("secretary"));
};

const isBankOwnedProperty = (deal) => {
  const owner1 = (deal.owners_name_1 || "").toLowerCase();
  const owner2 = (deal.owners_name_2 || "").toLowerCase();
  return hasBankWord(owner1) || hasBankWord(owner2);
};

const isSheriffSaleProperty = (deal) => Boolean(deal.is_sheriff_sale);
const matchesStatusFilters = ({
  deal,
  distressedOnly,
  bankOwnedOnly,
  sheriffSaleOnly,
}) => {
  const selectedFilters = [
    distressedOnly && isDistressedProperty(deal),
    bankOwnedOnly && isBankOwnedProperty(deal),
    sheriffSaleOnly && isSheriffSaleProperty(deal),
  ];

  const anyFilterSelected = distressedOnly || bankOwnedOnly || sheriffSaleOnly;
  return anyFilterSelected ? selectedFilters.some(Boolean) : true;
};

const DealsTable = ({ deals }) => (
  <table width="100%" border="1" cellPadding="8">
    <thead>
      <tr>
        <th>Parcel ID</th>
        <th>Address</th>
        <th>Municipality</th>
        <th>Owner 1</th>
        <th>Owner 2</th>
        <th>Mailing Address</th>
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
        const isBankOwned = isBankOwnedProperty(d);
        const isSheriffSale = isSheriffSaleProperty(d);
        const mailingAddress = [
          d.mail_address_1,
          d.mail_address_2,
          d.mail_address_3,
        ]
          .filter((line) => line && String(line).trim())
          .join(", ");

        return (
          <tr
            key={d.parcel_id}
            style={{
              backgroundColor: isSheriffSale
                ? "#fff6cc"
                : isBankOwned
                  ? "#e6f0ff"
                  : isDistressed
                    ? "#ffe6e6"
                    : "white",
            }}
          >
            <td>{d.parcel_id}</td>
            <td>{d.address}</td>
            <td>{formatMuni(d.muni)}</td>
            <td>{d.owners_name_1 || "—"}</td>
            <td>{d.owners_name_2 || "—"}</td>
            <td>{mailingAddress || "—"}</td>
            <td>
              {totalAssessedValue != null
                ? `$${totalAssessedValue.toLocaleString()}`
                : "—"}
            </td>
            <td>
              <b>{score.toFixed(2)}</b>
            </td>
            <td>{d.sale_type || "—"}</td>
            <td>
              {isSheriffSale
                ? "⚖️ Sheriff Sale"
                : isBankOwned
                  ? "🏦 Bank Owned"
                  : isDistressed
                    ? "🔥 Distressed"
                    : "—"}
            </td>
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
  const [showBankOwnedOnly, setShowBankOwnedOnly] = useState(false);
  const [showSheriffSaleOnly, setShowSheriffSaleOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 50,
    total: 0,
    total_pages: 1,
  });
  const [isSearchMode, setIsSearchMode] = useState(false);

  const fetchDeals = ({
    distressedOnly = false,
    bankOwnedOnly = false,
    sheriffSaleOnly = false,
    pageNumber = 1,
  } = {}) => {
    setLoading(true);
    setIsSearchMode(false);

    axios
      .get(`${API}/deals`, {
        params: {
          muni: muni || undefined,
          min_score: minScore || 0,
          distressed_only: distressedOnly || undefined,
          bank_owned_only: bankOwnedOnly || undefined,
          sheriff_sale_only: sheriffSaleOnly || undefined,
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
        setDeals(
          results.filter((deal) => {
            return matchesStatusFilters({
              deal,
              distressedOnly,
              bankOwnedOnly,
              sheriffSaleOnly,
            });
          }),
        );
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
      return fetchDeals({
        distressedOnly: showDistressedOnly,
        bankOwnedOnly: showBankOwnedOnly,
        sheriffSaleOnly: showSheriffSaleOnly,
        pageNumber: 1,
      });
    }

    setLoading(true);
    setIsSearchMode(true);

    axios
      .get(`${API}/search`, {
        params: { q: query, limit: 50 },
      })
      .then((res) => {
        const results = res.data.results || [];
        setDeals(
          results.filter((deal) => {
            return matchesStatusFilters({
              deal,
              distressedOnly: showDistressedOnly,
              bankOwnedOnly: showBankOwnedOnly,
              sheriffSaleOnly: showSheriffSaleOnly,
            });
          }),
        );
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
    fetchDeals({
      distressedOnly: showDistressedOnly,
      bankOwnedOnly: showBankOwnedOnly,
      sheriffSaleOnly: showSheriffSaleOnly,
      pageNumber: 1,
    });
  };

  const goToNextPage = () => {
    if (isSearchMode || page >= pagination.total_pages) return;
    fetchDeals({
      distressedOnly: showDistressedOnly,
      bankOwnedOnly: showBankOwnedOnly,
      sheriffSaleOnly: showSheriffSaleOnly,
      pageNumber: page + 1,
    });
  };

  const goToPreviousPage = () => {
    if (isSearchMode || page <= 1) return;
    fetchDeals({
      distressedOnly: showDistressedOnly,
      bankOwnedOnly: showBankOwnedOnly,
      sheriffSaleOnly: showSheriffSaleOnly,
      pageNumber: page - 1,
    });
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

        <select value={muni} onChange={(e) => setMuni(e.target.value)}>
          <option value="">All municipalities</option>
          {Object.entries(MUNICIPALITIES).map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>

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

        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input
            type="checkbox"
            checked={showBankOwnedOnly}
            onChange={(e) => setShowBankOwnedOnly(e.target.checked)}
          />
          Bank owned properties only
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input
            type="checkbox"
            checked={showSheriffSaleOnly}
            onChange={(e) => setShowSheriffSaleOnly(e.target.checked)}
          />
          Sheriff sale only
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
