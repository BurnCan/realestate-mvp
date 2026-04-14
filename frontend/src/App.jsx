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

const matchesMunicipality = (deal, selectedMuni) => {
  if (!selectedMuni) return true;
  return normalizeMuniCode(deal.muni) === normalizeMuniCode(selectedMuni);
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
}) => {
  const selectedFilters = [
    distressedOnly && isDistressedProperty(deal),
    bankOwnedOnly && isBankOwnedProperty(deal),
    sheriffSaleOnly && isSheriffSaleProperty(deal),
    ownerOccupantOnly && isOwnerOccupantProperty(deal),
  ];

  const anyFilterSelected =
    distressedOnly || bankOwnedOnly || sheriffSaleOnly || ownerOccupantOnly;
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
  const [muni, setMuni] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [search, setSearch] = useState("");
  const [searchMode, setSearchMode] = useState("all");
  const [minYearBuilt, setMinYearBuilt] = useState("");
  const [maxYearBuilt, setMaxYearBuilt] = useState("");
  const [loading, setLoading] = useState(false);
  const [showDistressedOnly, setShowDistressedOnly] = useState(false);
  const [showBankOwnedOnly, setShowBankOwnedOnly] = useState(false);
  const [showSheriffSaleOnly, setShowSheriffSaleOnly] = useState(false);
  const [showOwnerOccupantOnly, setShowOwnerOccupantOnly] = useState(false);
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
    ownerOccupantOnly = false,
    pageNumber = 1,
  } = {}) => {
    setLoading(true);
    setIsSearchMode(false);
    const parsedMinYearBuilt = minYearBuilt ? Number(minYearBuilt) : undefined;
    const parsedMaxYearBuilt = maxYearBuilt ? Number(maxYearBuilt) : undefined;

    axios
      .get(`${API}/deals`, {
        params: {
          muni: muni || undefined,
          min_score: minScore || 0,
          min_year_built: parsedMinYearBuilt,
          max_year_built: parsedMaxYearBuilt,
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
              ownerOccupantOnly,
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
        pageNumber: 1,
      });
    }

    setLoading(true);
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
            }) && matchesMunicipality(deal, muni) && (deal.deal_score ?? 0) >= minScore && matchesYearBuiltRange({
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
      pageNumber: 1,
    });
  };

  const goToNextPage = () => {
    if (isSearchMode || page >= pagination.total_pages) return;
    fetchDeals({
      distressedOnly: showDistressedOnly,
      bankOwnedOnly: showBankOwnedOnly,
      sheriffSaleOnly: showSheriffSaleOnly,
      ownerOccupantOnly: showOwnerOccupantOnly,
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

        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input
            type="checkbox"
            checked={showOwnerOccupantOnly}
            onChange={(e) => setShowOwnerOccupantOnly(e.target.checked)}
          />
          Owner occupant only
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
};

const DivorceDashboard = () => {
  const [divorceCases, setDivorceCases] = useState([]);
  const [divorceLoading, setDivorceLoading] = useState(false);
  const [divorcePagination, setDivorcePagination] = useState({
    page: 1,
    limit: 100,
    total: 0,
    total_pages: 1,
  });

  const fetchDivorceCases = (pageNumber = 1) => {
    setDivorceLoading(true);
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
      .finally(() => setDivorceLoading(false));
  };

  useEffect(() => {
    fetchDivorceCases();
  }, []);

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h1>⚖️ Divorce Cases Dashboard</h1>
      {divorceLoading && <p>Loading divorce cases...</p>}
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
