import { useEffect, useState } from "react";
import axios from "axios";

const API = import.meta.env.VITE_API_BASE_URL || "/api";

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

const normalizeMuniCode = (muniCode) => {
  const raw = String(muniCode || "").trim();
  if (!raw) return "";
  if (!/^\d+$/.test(raw)) return raw.toLowerCase();
  return String(Number.parseInt(raw, 10));
};

const formatOwnershipChangeDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
};

const matchesMunicipality = (deal, selectedMunis) => {
  if (!selectedMunis.length) return true;
  const dealMuni = normalizeMuniCode(deal.muni);
  return selectedMunis.some((selectedMuni) => (
    dealMuni === normalizeMuniCode(selectedMuni)
  ));
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
const isOwnerOccupantProperty = (deal) => {
  const propertyAddress = String(deal.address || "")
    .toLowerCase()
    .trim();
  const mailingAddress = [deal.mail_address_1, deal.mail_address_2, deal.mail_address_3]
    .filter((line) => line && String(line).trim())
    .join(" ")
    .toLowerCase()
    .trim();

  if (!propertyAddress || !mailingAddress) return false;

  return (
    mailingAddress.includes(propertyAddress) ||
    propertyAddress.includes(mailingAddress)
  );
};
const matchesStatusFilters = ({
  deal,
  distressedOnly,
  bankOwnedOnly,
  sheriffSaleOnly,
  ownerOccupantOnly,
  recentDivorceOnly,
}) => {
  const selectedFilters = [
    distressedOnly && isDistressedProperty(deal),
    bankOwnedOnly && isBankOwnedProperty(deal),
    sheriffSaleOnly && isSheriffSaleProperty(deal),
    ownerOccupantOnly && isOwnerOccupantProperty(deal),
    recentDivorceOnly && Boolean(deal.recent_divorce),
  ];

  const anyFilterSelected =
    distressedOnly || bankOwnedOnly || sheriffSaleOnly || ownerOccupantOnly || recentDivorceOnly;
  return anyFilterSelected ? selectedFilters.some(Boolean) : true;
};

const matchesYearBuiltRange = ({ deal, minYearBuilt, maxYearBuilt }) => {
  if (!minYearBuilt && !maxYearBuilt) return true;
  const yearBuilt = Number(deal.year_built);
  if (!Number.isFinite(yearBuilt)) return false;
  if (minYearBuilt && yearBuilt < minYearBuilt) return false;
  if (maxYearBuilt && yearBuilt > maxYearBuilt) return false;
  return true;
};

const DealsTable = ({ deals }) => (
  <table width="100%" border="1" cellPadding="8">
    <thead>
      <tr>
        <th>Parcel ID</th>
        <th>Address</th>
        <th>Municipality</th>
        <th>Year Built</th>
        <th>Owner 1</th>
        <th>Owner 2</th>
        <th>Ownership Change Date</th>
        <th>Mailing Address</th>
        <th>Total Assessed Value</th>
        <th>Deal Score</th>
        <th>Sale Type</th>
        <th>Status</th>
        <th>Owner Occupant</th>
        <th>Recent Divorce</th>
        <th>Divorce Case Status</th>
        <th>Divorce Date Opened</th>
      </tr>
    </thead>

    <tbody>
      {deals.map((d) => {
        const score = d.deal_score ?? 0;
        const totalAssessedValue = d.total_assessed_value ?? d.assessed_value ?? null;
        const isDistressed = isDistressedProperty(d);
        const isBankOwned = isBankOwnedProperty(d);
        const isSheriffSale = isSheriffSaleProperty(d);
        const isOwnerOccupant = isOwnerOccupantProperty(d);
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
            <td>{d.year_built || "—"}</td>
            <td>{d.owners_name_1 || "—"}</td>
            <td>{d.owners_name_2 || "—"}</td>
            <td>{formatOwnershipChangeDate(d.ownership_change_date)}</td>
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
            <td>{isOwnerOccupant ? "✅ Yes" : "—"}</td>
            <td>{d.recent_divorce ? "✅ Yes" : "—"}</td>
            <td>{d.divorce_case_status || "—"}</td>
            <td>{formatOwnershipChangeDate(d.divorce_date_opened)}</td>
          </tr>
        );
      })}
    </tbody>
  </table>
);

const DivorceCasesTable = ({ cases }) => (
  <table width="100%" border="1" cellPadding="8">
    <thead>
      <tr>
        <th>Case Number</th>
        <th>Participants</th>
        <th>Category</th>
        <th>Date Opened</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {cases.map((c) => (
        <tr key={c.case_number}>
          <td>{c.case_number || "—"}</td>
          <td>{c.case_participants || "—"}</td>
          <td>{c.case_category || "—"}</td>
          <td>{formatOwnershipChangeDate(c.date_opened)}</td>
          <td>{c.status || "—"}</td>
        </tr>
      ))}
    </tbody>
  </table>
);

const Navigation = ({ currentPath, navigate }) => (
  <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
    <button
      onClick={() => navigate("/")}
      style={{ fontWeight: currentPath === "/" ? "bold" : "normal" }}
    >
      Real Estate Dashboard
    </button>
    <button
      onClick={() => navigate("/divorces")}
      style={{ fontWeight: currentPath === "/divorces" ? "bold" : "normal" }}
    >
      Divorce Cases
    </button>
  </div>
);

const DealsDashboard = () => {
  const [deals, setDeals] = useState([]);
  const [selectedMunis, setSelectedMunis] = useState([]);
  const [minScore, setMinScore] = useState(0);
  const [search, setSearch] = useState("");
  const [searchMode, setSearchMode] = useState("all");
  const [minYearBuilt, setMinYearBuilt] = useState("");
  const [maxYearBuilt, setMaxYearBuilt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showDistressedOnly, setShowDistressedOnly] = useState(false);
  const [showBankOwnedOnly, setShowBankOwnedOnly] = useState(false);
  const [showSheriffSaleOnly, setShowSheriffSaleOnly] = useState(false);
  const [showOwnerOccupantOnly, setShowOwnerOccupantOnly] = useState(false);
  const [showRecentDivorceOnly, setShowRecentDivorceOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 50,
    total: 0,
    total_pages: 1,
  });
  const [isSearchMode, setIsSearchMode] = useState(false);
  const includeFilterToggles = [
    {
      key: "distressed",
      label: "Distressed properties",
      checked: showDistressedOnly,
      onChange: setShowDistressedOnly,
    },
    {
      key: "bankOwned",
      label: "Bank owned properties",
      checked: showBankOwnedOnly,
      onChange: setShowBankOwnedOnly,
    },
    {
      key: "sheriffSale",
      label: "Sheriff sale",
      checked: showSheriffSaleOnly,
      onChange: setShowSheriffSaleOnly,
    },
    {
      key: "ownerOccupant",
      label: "Owner occupant",
      checked: showOwnerOccupantOnly,
      onChange: setShowOwnerOccupantOnly,
    },
    {
      key: "recentDivorce",
      label: "Recent divorce",
      checked: showRecentDivorceOnly,
      onChange: setShowRecentDivorceOnly,
    },
  ];

  const fetchDeals = ({
    distressedOnly = false,
    bankOwnedOnly = false,
    sheriffSaleOnly = false,
    ownerOccupantOnly = false,
    recentDivorceOnly = false,
    pageNumber = 1,
  } = {}) => {
    setLoading(true);
    setError("");
    setIsSearchMode(false);
    const parsedMinYearBuilt = minYearBuilt ? Number(minYearBuilt) : undefined;
    const parsedMaxYearBuilt = maxYearBuilt ? Number(maxYearBuilt) : undefined;

    axios
      .get(`${API}/deals`, {
        params: {
          munis: selectedMunis.length ? selectedMunis.join(",") : undefined,
          min_score: minScore || 0,
          min_year_built: parsedMinYearBuilt,
          max_year_built: parsedMaxYearBuilt,
          distressed_only: distressedOnly || undefined,
          bank_owned_only: bankOwnedOnly || undefined,
          sheriff_sale_only: sheriffSaleOnly || undefined,
          recent_divorce_only: recentDivorceOnly || undefined,
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
              ownerOccupantOnly,
              recentDivorceOnly,
            }) && matchesYearBuiltRange({
              deal,
              minYearBuilt: parsedMinYearBuilt,
              maxYearBuilt: parsedMaxYearBuilt,
            });
          }),
        );
        setPagination(nextPagination);
        setPage(nextPagination.page);
      })
      .catch(() => {
        setDeals([]);
        setPagination({ page: 1, limit: 50, total: 0, total_pages: 1 });
        setPage(1);
        setError("Could not load properties. Make sure the API server is running.");
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
        ownerOccupantOnly: showOwnerOccupantOnly,
        recentDivorceOnly: showRecentDivorceOnly,
        pageNumber: 1,
      });
    }

    setLoading(true);
    setError("");
    setIsSearchMode(true);
    const parsedMinYearBuilt = minYearBuilt ? Number(minYearBuilt) : undefined;
    const parsedMaxYearBuilt = maxYearBuilt ? Number(maxYearBuilt) : undefined;

    axios
      .get(`${API}/search`, {
        params: { q: query, mode: searchMode, limit: 50 },
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
              ownerOccupantOnly: showOwnerOccupantOnly,
              recentDivorceOnly: showRecentDivorceOnly,
            }) && matchesMunicipality(deal, selectedMunis) && (deal.deal_score ?? 0) >= minScore && matchesYearBuiltRange({
              deal,
              minYearBuilt: parsedMinYearBuilt,
              maxYearBuilt: parsedMaxYearBuilt,
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
      .catch(() => {
        setDeals([]);
        setPagination({ page: 1, limit: 50, total: 0, total_pages: 1 });
        setPage(1);
        setError("Could not search properties. Make sure the API server is running.");
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
      ownerOccupantOnly: showOwnerOccupantOnly,
      recentDivorceOnly: showRecentDivorceOnly,
      pageNumber: 1,
    });
  };

  const toggleMunicipality = (code) => {
    setSelectedMunis((current) => (
      current.includes(code)
        ? current.filter((selectedCode) => selectedCode !== code)
        : [...current, code]
    ));
  };

  const goToNextPage = () => {
    if (isSearchMode || page >= pagination.total_pages) return;
    fetchDeals({
      distressedOnly: showDistressedOnly,
      bankOwnedOnly: showBankOwnedOnly,
      sheriffSaleOnly: showSheriffSaleOnly,
      ownerOccupantOnly: showOwnerOccupantOnly,
      recentDivorceOnly: showRecentDivorceOnly,
      pageNumber: page + 1,
    });
  };

  const goToPreviousPage = () => {
    if (isSearchMode || page <= 1) return;
    fetchDeals({
      distressedOnly: showDistressedOnly,
      bankOwnedOnly: showBankOwnedOnly,
      sheriffSaleOnly: showSheriffSaleOnly,
      ownerOccupantOnly: showOwnerOccupantOnly,
      recentDivorceOnly: showRecentDivorceOnly,
      pageNumber: page - 1,
    });
  };

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h1>🏡 Real Estate Results Dashboard</h1>

      <div style={{ display: "flex", gap: 10, marginBottom: 20, alignItems: "center" }}>
        <input
          placeholder={
            searchMode === "address"
              ? "Search address..."
              : searchMode === "owner"
                ? "Search owner..."
                : "Search address or owner..."
          }
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && searchDeals(search)}
        />
        <select value={searchMode} onChange={(e) => setSearchMode(e.target.value)}>
          <option value="all">All fields</option>
          <option value="address">Address</option>
          <option value="owner">Owner</option>
        </select>
        <button onClick={() => searchDeals(search)}>Search</button>
        <input
          type="number"
          placeholder="Min Score"
          value={minScore}
          onChange={(e) => setMinScore(Number(e.target.value))}
        />
      </div>

      <fieldset
        style={{
          border: "1px solid #ccc",
          borderRadius: 6,
          padding: 12,
          marginBottom: 16,
        }}
      >
        <legend style={{ padding: "0 6px", fontWeight: "bold" }}>Include Filters</legend>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div
            style={{
              border: "1px solid #ddd",
              borderRadius: 4,
              padding: 8,
              minWidth: 240,
              maxHeight: 180,
              overflowY: "auto",
            }}
          >
            <label style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <input
                type="checkbox"
                checked={!selectedMunis.length}
                onChange={(e) => {
                  if (e.target.checked) setSelectedMunis([]);
                }}
              />
              All municipalities
            </label>

            {Object.entries(MUNICIPALITIES).map(([code, name]) => (
              <label
                key={code}
                style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}
              >
                <input
                  type="checkbox"
                  checked={selectedMunis.includes(code)}
                  onChange={() => toggleMunicipality(code)}
                />
                {name}
              </label>
            ))}
          </div>

          <input
            type="number"
            placeholder="Min Year Built"
            value={minYearBuilt}
            onChange={(e) => setMinYearBuilt(e.target.value)}
          />

          <input
            type="number"
            placeholder="Max Year Built"
            value={maxYearBuilt}
            onChange={(e) => setMaxYearBuilt(e.target.value)}
          />

          {includeFilterToggles.map((filter) => (
            <label
              key={filter.key}
              style={{ display: "flex", alignItems: "center", gap: 6 }}
            >
              <input
                type="checkbox"
                checked={filter.checked}
                onChange={(e) => filter.onChange(e.target.checked)}
              />
              {filter.label}
            </label>
          ))}

          <button onClick={applyFilters}>Apply Filters</button>
        </div>
      </fieldset>

      {loading && <p>Loading results...</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}
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
};

const DivorceDashboard = () => {
  const [divorceCases, setDivorceCases] = useState([]);
  const [divorceLoading, setDivorceLoading] = useState(false);
  const [divorceError, setDivorceError] = useState("");
  const [divorcePagination, setDivorcePagination] = useState({
    page: 1,
    limit: 100,
    total: 0,
    total_pages: 1,
  });

  const fetchDivorceCases = (pageNumber = 1) => {
    setDivorceLoading(true);
    setDivorceError("");
    axios
      .get(`${API}/divorce-cases`, {
        params: {
          limit: 100,
          page: pageNumber,
        },
      })
      .then((res) => {
        setDivorceCases(res.data.results || []);
        setDivorcePagination(
          res.data.pagination || {
            page: pageNumber,
            limit: 100,
            total: (res.data.results || []).length,
            total_pages: 1,
          },
        );
      })
      .catch(() => {
        setDivorceCases([]);
        setDivorcePagination({ page: 1, limit: 100, total: 0, total_pages: 1 });
        setDivorceError("Could not load divorce cases. Make sure the API server is running.");
      })
      .finally(() => setDivorceLoading(false));
  };

  useEffect(() => {
    fetchDivorceCases();
  }, []);

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h1>⚖️ Divorce Cases Dashboard</h1>
      {divorceLoading && <p>Loading divorce cases...</p>}
      {divorceError && <p style={{ color: "crimson" }}>{divorceError}</p>}
      <p>
        Showing page {divorcePagination.page} of {Math.max(divorcePagination.total_pages, 1)} (
        {divorcePagination.total.toLocaleString()} total cases)
      </p>
      <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
        <button
          onClick={() => fetchDivorceCases(divorcePagination.page - 1)}
          disabled={divorcePagination.page <= 1}
        >
          ← Previous
        </button>
        <button
          onClick={() => fetchDivorceCases(divorcePagination.page + 1)}
          disabled={divorcePagination.page >= divorcePagination.total_pages}
        >
          Next →
        </button>
      </div>
      <DivorceCasesTable cases={divorceCases} />
    </div>
  );
};

const getCurrentPath = () => {
  const path = window.location.pathname || "/";
  if (path === "/divorces") return "/divorces";
  return "/";
};

export default function App() {
  const [currentPath, setCurrentPath] = useState(getCurrentPath);

  useEffect(() => {
    const onPopState = () => setCurrentPath(getCurrentPath());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = (path) => {
    if (path === currentPath) return;
    window.history.pushState({}, "", path);
    setCurrentPath(path);
  };

  return (
    <>
      <Navigation currentPath={currentPath} navigate={navigate} />
      {currentPath === "/divorces" ? <DivorceDashboard /> : <DealsDashboard />}
    </>
  );
}
