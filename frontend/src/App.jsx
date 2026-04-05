import { useEffect, useState } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000";

export default function App() {
  const [deals, setDeals] = useState([]);

   const [muni, setMuni] = useState("");
   const [minScore, setMinScore] = useState(0);
   const [search, setSearch] = useState("");
   const [loading, setLoading] = useState(false);

<<<<<<< HEAD
   // -------------------------
   // Fetch main deals feed
   // -------------------------
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
=======
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
>>>>>>> refs/remotes/origin/dev

   // -------------------------
   // Search endpoint
   // -------------------------
   const searchDeals = (q) => {
     const query = (q || "").trim();
     if (!query) return fetchDeals();

     setLoading(true);

<<<<<<< HEAD
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
         <button onClick={() => searchDeals(search)}>Search</button>


         />
=======
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
>>>>>>> refs/remotes/origin/dev

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
             const saleType = (d.sale_type || "").toLowerCase();
             const score = d.deal_score ?? 0;
             const totalAssessedValue =
               d.total_assessed_value ?? d.assessed_value ?? null;

             // -------------------------
             // improved distress logic
             // -------------------------
             const isDistressed =
               saleType.includes("foreclosure") ||
               saleType.includes("reo") ||
               saleType.includes("bank") ||
               saleType.includes("lien") ||
               score >= 2.0; // matches log-based scoring better

<<<<<<< HEAD
             return (
               <tr
                 key={d.parcel_id}
                 style={{
                   backgroundColor: isDistressed ? "#ffe6e6" : "white",
                 }}
               >
                 <td>{d.parcel_id}</td>
                 <td>{d.address}</td>
                 <td>{d.owners_name_1 || "—"}</td>
                 <td>{d.owners_name_2 || "—"}</td>
                 <td>{d.muni}</td>

                 <td>
                   {totalAssessedValue != null
                     ? `$${totalAssessedValue.toLocaleString()}`
                     : "—"}
                 </td>
=======
      {/* -------------------------
          Table
      -------------------------- */}
      <table width="100%" border="1" cellPadding="8">
        <thead>
          <tr>
            <th>Parcel ID</th>
            <th>Address</th>
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
            const saleType = (d.sale_type || "").toLowerCase();
            const score = d.deal_score ?? 0;
            const totalAssessedValue =
              d.total_assessed_value ?? d.assessed_value ?? null;
>>>>>>> refs/remotes/origin/dev

                 <td>
                   <b>{score.toFixed(2)}</b>
                 </td>

<<<<<<< HEAD
                 <td>{d.sale_type || "—"}</td>
=======
            return (
              <tr
                key={d.parcel_id}
                style={{
                  backgroundColor: isDistressed ? "#ffe6e6" : "white",
                }}
              >
                <td>{d.parcel_id}</td>
                <td>{d.address}</td>
                <td>{d.owners_name_1 || "—"}</td>
                <td>{d.owners_name_2 || "—"}</td>
                <td>{d.muni}</td>
                <td>
                  {totalAssessedValue != null
                    ? `$${totalAssessedValue.toLocaleString()}`
                    : "—"}
                </td>
>>>>>>> refs/remotes/origin/dev

                 <td>{isDistressed ? "🔥 Distressed" : "—"}</td>
               </tr>
             );
           })}
         </tbody>
       </table>
     </div>
   );
 }
