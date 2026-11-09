import React from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";

/**
 * Barres verticales groupées par mois (statistiques mensuelles du tableau de bord).
 * ``keepOrder`` : légende et infobulle dans l'ordre de ``bars`` (Recharts trie sinon par libellé).
 */
export default function MonthlyBarChart({ data, bars, xKey = "mois", height = 280, keepOrder = false }) {
  const sorter = keepOrder ? { itemSorter: null } : {};
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data || []} barGap={4}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f6" />
        <XAxis dataKey={xKey} axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "#64748b" }} />
        <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "#64748b" }} allowDecimals={false} />
        <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13 }} {...sorter} />
        <Legend wrapperStyle={{ fontSize: 13 }} {...sorter} />
        {(bars || []).map((bar) => (
          <Bar key={bar.key} dataKey={bar.key} name={bar.label} fill={bar.color} radius={[4, 4, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
