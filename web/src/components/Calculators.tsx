import { useState } from "react";
import type { ToolResult } from "../types";
import { api } from "../api/client";
import { Callout, Spinner } from "./Primitives";
import { ToolResultView } from "./ToolResultView";

/**
 * Direct calculator access -- no LLM in the path.
 *
 * These hit the same MCP tools the agent calls, so the answers are identical
 * by construction rather than by convention. Keeping them reachable without the
 * agent means the product still works when the model is throttled or down,
 * and it is faster and cheaper when the user already knows what they want.
 */

type Tab = "mortgage" | "savings" | "gains";

function Field({
  label, value, onChange, step = "any", min, placeholder, hint, type = "number",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  step?: string;
  min?: number;
  placeholder?: string;
  hint?: string;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>
        {label}
      </span>
      <input
        type={type}
        value={value}
        step={step}
        min={min}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="tnum w-full rounded-lg border px-2.5 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
        style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
      />
      {hint && (
        <span className="mt-0.5 block text-[10px]" style={{ color: "var(--text-faint)" }}>
          {hint}
        </span>
      )}
    </label>
  );
}

function Select({
  label, value, onChange, options,
}: {
  label: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border px-2.5 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
        style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  );
}

/** Blank means "not supplied" -- the backend then fetches a live rate. */
const num = (v: string): number | undefined =>
  v.trim() === "" ? undefined : Number(v);

export function Calculators() {
  const [tab, setTab] = useState<Tab>("mortgage");
  const [result, setResult] = useState<ToolResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Mortgage
  const [price, setPrice] = useState("620000");
  const [down, setDown] = useState("124000");
  const [rate, setRate] = useState("");
  const [term, setTerm] = useState("30");
  const [extra, setExtra] = useState("0");
  const [compareTerms, setCompareTerms] = useState(false);

  // Savings
  const [deposit, setDeposit] = useState("25000");
  const [apy, setApy] = useState("");
  const [years, setYears] = useState("20");
  const [monthly, setMonthly] = useState("600");

  // Capital gains
  const [proceeds, setProceeds] = useState("180000");
  const [basis, setBasis] = useState("120000");
  const [income, setIncome] = useState("95000");
  const [status, setStatus] = useState("single");
  const [stateRate, setStateRate] = useState("0");
  const [longTerm, setLongTerm] = useState("true");

  async function run(fn: () => Promise<ToolResult>) {
    setBusy(true); setError(null);
    try {
      setResult(await fn());
    } catch (e) {
      setError((e as Error).message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  const submit = () => {
    if (tab === "mortgage") {
      const loan = (Number(price) || 0) - (Number(down) || 0);
      if (compareTerms) {
        return run(() => api.calcCompare({
          options: [
            { label: "30-year", loan_amount: loan, annual_rate_percent: num(rate), term_years: 30 },
            { label: "15-year", loan_amount: loan, term_years: 15 },
            ...(Number(extra) > 0
              ? [{ label: `30-year +$${extra}/mo`, loan_amount: loan,
                   annual_rate_percent: num(rate), term_years: 30,
                   extra_monthly_payment: Number(extra) }]
              : []),
          ],
        }));
      }
      return run(() => api.calcMortgage({
        home_price: Number(price), down_payment: Number(down),
        annual_rate_percent: num(rate), term_years: Number(term),
        extra_monthly_payment: Number(extra) || 0,
      }));
    }
    if (tab === "savings") {
      return run(() => api.calcSavings({
        initial_deposit: Number(deposit), apy_percent: num(apy),
        years: Number(years), monthly_contribution: Number(monthly),
      }));
    }
    return run(() => api.calcCapitalGains({
      sale_proceeds: Number(proceeds), cost_basis: Number(basis),
      is_long_term: longTerm === "true", other_taxable_income: Number(income),
      filing_status: status, state_tax_rate_percent: Number(stateRate) || 0,
    }));
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: "mortgage", label: "Mortgage" },
    { id: "savings", label: "Savings" },
    { id: "gains", label: "Capital gains" },
  ];

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(320px,1fr)_2fr]">
      <div className="space-y-4">
      <div className="flex gap-1 rounded-lg p-1" style={{ background: "var(--surface-2)" }}>
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => { setTab(t.id); setResult(null); setError(null); }}
            className="flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors"
            style={{
              background: tab === t.id ? "var(--surface)" : "transparent",
              color: tab === t.id ? "var(--text)" : "var(--text-muted)",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div
        className="rounded-xl border p-4"
        style={{ background: "var(--surface)", borderColor: "var(--border)" }}
      >
        {tab === "mortgage" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Home price" value={price} onChange={setPrice} min={0} />
            <Field label="Down payment" value={down} onChange={setDown} min={0} />
            <Field label="Rate (%)" value={rate} onChange={setRate}
                   placeholder="live" hint="Blank uses today's average" />
            <Field label="Term (years)" value={term} onChange={setTerm} min={1} />
            <Field label="Extra monthly" value={extra} onChange={setExtra} min={0} />
            <label className="flex items-end gap-2 pb-1.5">
              <input
                type="checkbox"
                checked={compareTerms}
                onChange={(e) => setCompareTerms(e.target.checked)}
                className="h-3.5 w-3.5"
              />
              <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                Compare 30 vs 15
              </span>
            </label>
          </div>
        )}

        {tab === "savings" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Initial deposit" value={deposit} onChange={setDeposit} min={0} />
            <Field label="Monthly contribution" value={monthly} onChange={setMonthly} min={0} />
            <Field label="APY (%)" value={apy} onChange={setApy}
                   placeholder="live" hint="Blank estimates from fed funds" />
            <Field label="Years" value={years} onChange={setYears} min={1} />
          </div>
        )}

        {tab === "gains" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Sale proceeds" value={proceeds} onChange={setProceeds} min={0} />
            <Field label="Cost basis" value={basis} onChange={setBasis} min={0} />
            <Field label="Other taxable income" value={income} onChange={setIncome} min={0}
                   hint="Gains stack on top of this" />
            <Select label="Filing status" value={status} onChange={setStatus} options={[
              { value: "single", label: "Single" },
              { value: "married_jointly", label: "Married filing jointly" },
              { value: "married_separately", label: "Married filing separately" },
              { value: "head_of_household", label: "Head of household" },
            ]} />
            <Select label="Holding period" value={longTerm} onChange={setLongTerm} options={[
              { value: "true", label: "Long-term (over 1 year)" },
              { value: "false", label: "Short-term (1 year or less)" },
            ]} />
            <Field label="State rate (%)" value={stateRate} onChange={setStateRate} min={0} />
          </div>
        )}

        <button
          onClick={submit}
          disabled={busy}
          className="mt-4 w-full rounded-lg py-2 text-xs font-semibold transition-opacity disabled:opacity-50"
          style={{ background: "var(--accent)", color: "#fff" }}
        >
          {busy ? "Calculating…" : "Calculate"}
        </button>
      </div>

        {busy && <Spinner label="Running the numbers…" />}
        {error && <Callout tone="danger">{error}</Callout>}
      </div>

      <div className="min-w-0">
        {result && !busy ? (
          <div className="animate-in"><ToolResultView result={result} /></div>
        ) : (
          <div
            className="flex h-full min-h-[360px] items-center justify-center rounded-xl border border-dashed"
            style={{ borderColor: "var(--border)" }}
          >
            <p className="max-w-xs px-6 text-center text-xs leading-relaxed"
               style={{ color: "var(--text-faint)" }}>
              Results and charts appear here. These run the same calculations the
              agent uses, without an LLM in the path.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
