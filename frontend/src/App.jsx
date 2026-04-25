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
const ORDINAL_BASE_WORDS = {
  first: 1,
  second: 2,
  third: 3,
  fourth: 4,
  fifth: 5,
  sixth: 6,
  seventh: 7,
  eighth: 8,
  ninth: 9,
  tenth: 10,
  eleventh: 11,
  twelfth: 12,
  thirteenth: 13,
  fourteenth: 14,
  fifteenth: 15,
  sixteenth: 16,
  seventeenth: 17,
  eighteenth: 18,
  nineteenth: 19,
  twentieth: 20,
  thirtieth: 30,
  fortieth: 40,
  fiftieth: 50,
  sixtieth: 60,
  seventieth: 70,
  eightieth: 80,
  ninetieth: 90,
};
const ORDINAL_TENS = {
  twenty: 20,
  thirty: 30,
  forty: 40,
  fifty: 50,
  sixty: 60,
  seventy: 70,
  eighty: 80,
  ninety: 90,
};
const ORDINAL_UNITS = {
  first: 1,
  second: 2,
  third: 3,
  fourth: 4,
  fifth: 5,
  sixth: 6,
  seventh: 7,
  eighth: 8,
  ninth: 9,
};
const ORDINAL_PHRASE_TO_NUMBER = [
  ...Object.entries(ORDINAL_BASE_WORDS),
  ...Object.entries(ORDINAL_TENS).flatMap(([tensWord, tensValue]) => (
    Object.entries(ORDINAL_UNITS).map(([unitWord, unitValue]) => (
      [`${tensWord} ${unitWord}`, tensValue + unitValue]
    ))
  )),
].sort((a, b) => b[0].length - a[0].length);

const normalizeOwnerOccupantAddress = (value) => {
  let text = String(value || "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9 ]/g, " ")
    .replace(/\b(\d+)(st|nd|rd|th)\b/g, "$1");

  ORDINAL_PHRASE_TO_NUMBER.forEach(([phrase, number]) => {
    text = text.replace(new RegExp(`\\b${phrase}\\b`, "g"), String(number));
  });

  return text.replace(/\s+/g, " ").trim();
};

const isOwnerOccupantProperty = (deal) => {
  const propertyAddress = normalizeOwnerOccupantAddress(deal.address);
  const mailingAddress = normalizeOwnerOccupantAddress([deal.mail_address_1, deal.mail_address_2, deal.mail_address_3]
    .filter((line) => line && String(line).trim())
    .join(" "));

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

const doesDealMatchFrontendFilters = ({
  deal,
  selectedMunis = [],
  distressedOnly = false,
  bankOwnedOnly = false,
  sheriffSaleOnly = false,
  ownerOccupantOnly = false,
  recentDivorceOnly = false,
  parsedMinYearBuilt,
  parsedMaxYearBuilt,
  enforceMunicipalityCheck = false,
}) => (
  matchesStatusFilters({
    deal,
    distressedOnly,
    bankOwnedOnly,
    sheriffSaleOnly,
    ownerOccupantOnly,
    recentDivorceOnly,
  })
  && matchesYearBuiltRange({
    deal,
    minYearBuilt: parsedMinYearBuilt,
    maxYearBuilt: parsedMaxYearBuilt,
  })
  && (!enforceMunicipalityCheck || matchesMunicipality(deal, selectedMunis))
);

const getMailingAddressLines = (deal) => (
  [deal.mail_address_1, deal.mail_address_2, deal.mail_address_3]
    .map((line) => String(line || "").trim())
    .filter((line) => line)
);

const formatMailingAddress = (deal) => getMailingAddressLines(deal).join(", ");

const escapeCsvValue = (value) => {
  const text = String(value ?? "");
  if (text.includes("\"") || text.includes(",") || text.includes("\n")) {
    return `"${text.replace(/"/g, "\"\"")}"`;
  }
  return text;
};

const trimZipToFiveDigits = (text) => (
  String(text || "").replace(/\b(\d{5})(?:-?\d{4})\b/g, "$1")
);

const splitMailingAddressForExport = (mailingAddress) => {
  const normalized = trimZipToFiveDigits(String(mailingAddress || "").trim());
  if (!normalized) {
    return { streetLine: "", cityStateZipLine: "" };
  }

  const commaIndex = normalized.indexOf(",");
  if (commaIndex < 0) {
    return { streetLine: normalized, cityStateZipLine: "" };
  }

  return {
    streetLine: normalized.slice(0, commaIndex).trim(),
    cityStateZipLine: normalized.slice(commaIndex + 1).trim(),
  };
};

const buildOwnerMailingMultilineCell = (row) => {
  const ownerName = String(row?.owner_name_1 || "").trim();
  const { streetLine, cityStateZipLine } = splitMailingAddressForExport(row?.mailing_address);
  const lines = [ownerName, streetLine, cityStateZipLine];
  if (!lines.some((line) => line)) {
    return "";
  }
  return lines.join("\n");
};

const downloadOwnerMailingCsvRows = (rows, filenamePrefix = "owners-mailing-addresses") => {
  const csvHeader = ["Owner + Mailing Address"];
  const csvRows = (rows || [])
    .map((row) => [buildOwnerMailingMultilineCell(row)])
    .filter(([cellValue]) => cellValue !== "");
  const csvText = [
    csvHeader.map(escapeCsvValue).join(","),
    ...csvRows.map((row) => row.map(escapeCsvValue).join(",")),
  ].join("\n");

  const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const now = new Date().toISOString().slice(0, 10);
  link.download = `${filenamePrefix}-${now}.csv`;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
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
        const totalAssessedValue = d.total_assessed_value ?? d.assessed_value ?? null;
        const isDistressed = isDistressedProperty(d);
        const isBankOwned = isBankOwnedProperty(d);
        const isSheriffSale = isSheriffSaleProperty(d);
        const isOwnerOccupant = isOwnerOccupantProperty(d);
        const mailingAddress = formatMailingAddress(d);

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
    <button
      onClick={() => navigate("/campaigns")}
      style={{ fontWeight: currentPath.startsWith("/campaigns") ? "bold" : "normal" }}
    >
      Campaigns
    </button>
  </div>
);

const DealsDashboard = () => {
  const [deals, setDeals] = useState([]);
  const [selectedMunis, setSelectedMunis] = useState([]);
  const [search, setSearch] = useState("");
  const [searchMode, setSearchMode] = useState("all");
  const [minYearBuilt, setMinYearBuilt] = useState("");
  const [maxYearBuilt, setMaxYearBuilt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [creatingCampaign, setCreatingCampaign] = useState(false);
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
          min_year_built: parsedMinYearBuilt,
          max_year_built: parsedMaxYearBuilt,
          distressed_only: distressedOnly || undefined,
          bank_owned_only: bankOwnedOnly || undefined,
          sheriff_sale_only: sheriffSaleOnly || undefined,
          recent_divorce_only: recentDivorceOnly || undefined,
          owner_occupant_only: ownerOccupantOnly || undefined,
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
            }) && matchesMunicipality(deal, selectedMunis) && matchesYearBuiltRange({
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

  const createCampaignFromCurrentFilters = async () => {
    const name = window.prompt("Enter a campaign name:");
    if (!name || !name.trim()) return;
    setCreatingCampaign(true);
    setError("");

    const createCampaignFromResponse = (response) => {
      const campaignPath = response?.data?.slug || response?.data?.id || response?.data?.campaign_id;
      if (campaignPath !== undefined && campaignPath !== null && String(campaignPath).trim() !== "") {
        window.history.pushState({}, "", `/campaigns/${campaignPath}`);
        // Use a generic Event for broader browser compatibility.
        window.dispatchEvent(new Event("popstate"));
      } else {
        setError("Campaign was created, but no campaign id was returned.");
      }
    };

    const fetchAllMatchingParcelIds = async () => {
      const distressedOnly = showDistressedOnly;
      const bankOwnedOnly = showBankOwnedOnly;
      const sheriffSaleOnly = showSheriffSaleOnly;
      const ownerOccupantOnly = showOwnerOccupantOnly;
      const recentDivorceOnly = showRecentDivorceOnly;
      const parsedMinYearBuilt = minYearBuilt ? Number(minYearBuilt) : undefined;
      const parsedMaxYearBuilt = maxYearBuilt ? Number(maxYearBuilt) : undefined;
      const uniqueParcelIds = new Set();

      if (isSearchMode && (search || "").trim()) {
        const response = await axios.get(`${API}/search`, {
          params: {
            q: search.trim(),
            mode: searchMode,
            limit: 100000,
          },
        });
        const results = response.data.results || [];
        results
          .filter((deal) => doesDealMatchFrontendFilters({
            deal,
            selectedMunis,
            distressedOnly,
            bankOwnedOnly,
            sheriffSaleOnly,
            ownerOccupantOnly,
            recentDivorceOnly,
            parsedMinYearBuilt,
            parsedMaxYearBuilt,
            enforceMunicipalityCheck: true,
          }))
          .forEach((deal) => {
            const parcelId = String(deal?.parcel_id || "").trim();
            if (parcelId) uniqueParcelIds.add(parcelId);
          });
      } else {
        const limit = 500;
        const baseParams = {
          munis: selectedMunis.length ? selectedMunis.join(",") : undefined,
          min_year_built: parsedMinYearBuilt,
          max_year_built: parsedMaxYearBuilt,
          distressed_only: distressedOnly || undefined,
          bank_owned_only: bankOwnedOnly || undefined,
          sheriff_sale_only: sheriffSaleOnly || undefined,
          recent_divorce_only: recentDivorceOnly || undefined,
          owner_occupant_only: ownerOccupantOnly || undefined,
          limit,
        };
        let pageNumber = 1;
        let totalPages = 1;

        while (pageNumber <= totalPages) {
          const response = await axios.get(`${API}/deals`, {
            params: {
              ...baseParams,
              page: pageNumber,
            },
          });
          const results = response.data.results || [];
          results
            .filter((deal) => doesDealMatchFrontendFilters({
              deal,
              selectedMunis,
              distressedOnly,
              bankOwnedOnly,
              sheriffSaleOnly,
              ownerOccupantOnly,
              recentDivorceOnly,
              parsedMinYearBuilt,
              parsedMaxYearBuilt,
            }))
            .forEach((deal) => {
              const parcelId = String(deal?.parcel_id || "").trim();
              if (parcelId) uniqueParcelIds.add(parcelId);
            });
          totalPages = Math.max(response.data.pagination?.total_pages || 1, 1);
          pageNumber += 1;
        }
      }

      return [...uniqueParcelIds];
    };

    try {
      const payload = {
        name: name.trim(),
        munis: selectedMunis.length ? selectedMunis.join(",") : undefined,
        min_year_built: minYearBuilt ? Number(minYearBuilt) : undefined,
        max_year_built: maxYearBuilt ? Number(maxYearBuilt) : undefined,
        distressed_only: showDistressedOnly,
        bank_owned_only: showBankOwnedOnly,
        sheriff_sale_only: showSheriffSaleOnly,
        owner_occupant_only: showOwnerOccupantOnly,
        recent_divorce_only: showRecentDivorceOnly,
        search_query: isSearchMode && search.trim() ? search.trim() : undefined,
        search_mode: searchMode,
      };
      try {
        const response = await axios.post(`${API}/campaigns`, payload);
        createCampaignFromResponse(response);
      } catch (error) {
        const detailText = String(error?.response?.data?.detail || "");
        const normalizedDetail = detailText.toLowerCase();
        const isNameValidationError = error?.response?.status === 400
          && normalizedDetail.includes("campaign name is required");
        if (isNameValidationError) throw error;

        // Retry with explicit parcel ids so campaign creation does not depend on
        // server-side filter resolution differences.
        const parcelIds = await fetchAllMatchingParcelIds();
        const fallbackResponse = await axios.post(`${API}/campaigns`, {
          ...payload,
          parcel_ids: parcelIds,
        });
        createCampaignFromResponse(fallbackResponse);
      }
    } catch (error) {
      const detail = error?.response?.data?.detail;
      if (typeof detail === "string" && detail.trim()) {
        setError(`Could not create campaign: ${detail}`);
      } else {
        setError("Could not create campaign.");
      }
    } finally {
      setCreatingCampaign(false);
    }
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
          <button onClick={createCampaignFromCurrentFilters} disabled={creatingCampaign}>
            {creatingCampaign ? "Creating Campaign..." : "Create Campaign"}
          </button>
        </div>
      </fieldset>

      {loading && <p>Loading results...</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <p>
        Showing page {pagination.page} of {Math.max(pagination.total_pages, 1)} (
        {(pagination.unique_total ?? pagination.total).toLocaleString()} unique properties,{" "}
        {pagination.total.toLocaleString()} total rows)
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
  if (path.startsWith("/campaigns")) return path;
  if (path === "/divorces") return "/divorces";
  return "/";
};

const CampaignsDashboard = ({ navigate }) => {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError("");
    axios
      .get(`${API}/campaigns`)
      .then((res) => setCampaigns(res.data.results || []))
      .catch(() => setError("Could not load campaigns."))
      .finally(() => setLoading(false));
  }, []);

  const handleDeleteCampaign = async (campaign) => {
    const campaignLabel = campaign.name || `campaign ${campaign.id}`;
    const shouldDelete = window.confirm(`Delete ${campaignLabel}? This cannot be undone.`);
    if (!shouldDelete) return;

    setDeletingId(campaign.id);
    setError("");
    try {
      await axios.delete(`${API}/campaigns/${campaign.slug || campaign.id}`);
      setCampaigns((prevCampaigns) => (
        prevCampaigns.filter((existingCampaign) => existingCampaign.id !== campaign.id)
      ));
    } catch {
      setError("Could not delete campaign.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h1>📬 Campaigns</h1>
      {loading && <p>Loading campaigns...</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {!loading && !campaigns.length && <p>No campaigns yet.</p>}
      {!!campaigns.length && (
        <table width="100%" border="1" cellPadding="8">
          <thead>
            <tr>
              <th>Name</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((campaign) => (
              <tr key={campaign.id}>
                <td>
                  <button onClick={() => navigate(`/campaigns/${campaign.slug || campaign.id}`)}>
                    {campaign.name}
                  </button>
                </td>
                <td>{formatOwnershipChangeDate(campaign.created_at)}</td>
                <td>
                  <button
                    onClick={() => handleDeleteCampaign(campaign)}
                    disabled={deletingId === campaign.id}
                  >
                    {deletingId === campaign.id ? "Deleting..." : "Delete"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

const CampaignDetailDashboard = ({ campaignIdentifier }) => {
  const [campaign, setCampaign] = useState(null);
  const [deals, setDeals] = useState([]);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 250,
    total: 0,
    total_pages: 1,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [exportingSnapshot, setExportingSnapshot] = useState(false);
  const [redirectUrlInput, setRedirectUrlInput] = useState("");
  const [savingRedirectUrl, setSavingRedirectUrl] = useState(false);

  useEffect(() => {
    setPage(1);
  }, [campaignIdentifier]);

  useEffect(() => {
    if (!campaignIdentifier) return;
    const fetchCampaignAndDeals = async () => {
      setLoading(true);
      setError("");
      try {
        const campaignResponse = await axios.get(
          `${API}/campaigns/${campaignIdentifier}`,
          { params: { page, limit: 250 } },
        );
        const campaignData = campaignResponse.data;
        setCampaign(campaignData);
        setDeals(campaignData?.deals || []);
        setRedirectUrlInput(campaignData?.redirect_url || "");
        setPagination(
          campaignData?.pagination || {
            page,
            limit: 250,
            total: campaignData?.results_count || 0,
            total_pages: 1,
          },
        );
      } catch {
        setCampaign(null);
        setDeals([]);
        setPagination({
          page: 1,
          limit: 250,
          total: 0,
          total_pages: 1,
        });
        setError("Could not load campaign details.");
      } finally {
        setLoading(false);
      }
    };
    fetchCampaignAndDeals();
  }, [campaignIdentifier, page]);

  const exportCampaignSnapshotToCsv = async () => {
    if (!campaignIdentifier) return;
    setExportingSnapshot(true);
    setError("");
    try {
      const response = await axios.get(
        `${API}/campaigns/${campaignIdentifier}/mailing-addresses`,
      );
      const mailingRows = response?.data?.rows || [];
      const campaignSlugOrId = campaign?.slug || campaign?.id || campaignIdentifier;
      downloadOwnerMailingCsvRows(
        mailingRows,
        `campaign-${campaignSlugOrId}-owners-mailing-addresses`,
      );
    } catch {
      setError("Could not export campaign snapshot CSV. Make sure the API server is running.");
    } finally {
      setExportingSnapshot(false);
    }
  };

  const saveCampaignRedirectUrl = async () => {
    if (!campaignIdentifier) return;
    setSavingRedirectUrl(true);
    setError("");
    try {
      const response = await axios.patch(
        `${API}/campaigns/${campaignIdentifier}`,
        { redirect_url: redirectUrlInput.trim() || null },
      );
      setCampaign((prevCampaign) => (
        prevCampaign ? { ...prevCampaign, redirect_url: response?.data?.redirect_url || null } : prevCampaign
      ));
    } catch {
      setError("Could not save tracker redirect URL.");
    } finally {
      setSavingRedirectUrl(false);
    }
  };

  const currentTrackerUrl = campaign
    ? new URL(`${API}${campaign.tracker_path}`, window.location.origin).toString()
    : "";
  const currentRedirectDestination = campaign
    ? (campaign.redirect_url || `/campaigns/${campaign.slug || campaign.id}`)
    : "";
  const currentFullRedirectUrl = currentRedirectDestination
    ? new URL(currentRedirectDestination, window.location.origin).toString()
    : "";

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      {loading && <p>Loading campaign...</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {campaign && (
        <>
          <h1>📬 {campaign.name}</h1>
          <p>Created: {formatOwnershipChangeDate(campaign.created_at)}</p>
          <p>Tracker visits: {(campaign.visitors || 0).toLocaleString()}</p>
          <p>
            Tracker URL:{" "}
            <a href={currentTrackerUrl} target="_blank" rel="noreferrer">
              {currentTrackerUrl}
            </a>
          </p>
          <p>
            Current Redirect URL:{" "}
            <a href={currentFullRedirectUrl} target="_blank" rel="noreferrer">
              {currentFullRedirectUrl}
            </a>
          </p>
          <div style={{ marginBottom: 10 }}>
            <label htmlFor="campaign-redirect-url">Change Redirect URL to: </label>
            <input
              id="campaign-redirect-url"
              type="text"
              value={redirectUrlInput}
              onChange={(e) => setRedirectUrlInput(e.target.value)}
              placeholder={`/campaigns/${campaign.slug || campaign.id}`}
              style={{ minWidth: 360, marginRight: 8 }}
            />
            <button onClick={saveCampaignRedirectUrl} disabled={savingRedirectUrl || loading}>
              {savingRedirectUrl ? "Saving..." : "Save Redirect URL"}
            </button>
          </div>
          <p>
            Showing {(pagination.total || campaign.results_count || 0).toLocaleString()} properties
            snapshotted at campaign creation, with{" "}
            {(campaign.unique_mailing_addresses_count || 0).toLocaleString()} unique mailing addresses
            after deduplication.
          </p>
          <p>
            Page {pagination.page} of {Math.max(pagination.total_pages, 1)} (
            {deals.length.toLocaleString()} shown on this page)
          </p>
          <div style={{ marginBottom: 10 }}>
            <button
              onClick={exportCampaignSnapshotToCsv}
              disabled={loading || exportingSnapshot}
            >
              {exportingSnapshot ? "Exporting CSV..." : "Export Owner + Mailing CSV"}
            </button>
            <button
              style={{ marginLeft: 8 }}
              onClick={() => setPage((prev) => Math.max(prev - 1, 1))}
              disabled={loading || page <= 1}
            >
              Previous
            </button>
            <button
              style={{ marginLeft: 8 }}
              onClick={() => setPage((prev) => prev + 1)}
              disabled={loading || page >= pagination.total_pages}
            >
              Next
            </button>
          </div>
          <DealsTable deals={deals} />
        </>
      )}
    </div>
  );
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
      {currentPath === "/divorces" && <DivorceDashboard />}
      {currentPath === "/" && <DealsDashboard />}
      {currentPath === "/campaigns" && <CampaignsDashboard navigate={navigate} />}
      {currentPath.startsWith("/campaigns/") && (
        <CampaignDetailDashboard campaignIdentifier={currentPath.split("/")[2]} />
      )}
    </>
  );
}
