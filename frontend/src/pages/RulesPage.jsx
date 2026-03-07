import { useEffect, useMemo, useState } from "react";

function RulesPage({ rules = [], menuRank = [], recommendations = {} }) {
  const [query, setQuery] = useState("");
  const [minLift, setMinLift] = useState(0);
  const [selectedItem, setSelectedItem] = useState("Burger");

  const toFixed = (value, digits = 2) => Number(value || 0).toFixed(digits);
  const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;

  const parseItems = (raw) => {
    if (Array.isArray(raw)) {
      return raw.map((item) => String(item).trim()).filter(Boolean);
    }
    return String(raw || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  };

  const normalizedRules = useMemo(
    () =>
      rules.map((row) => {
        const antecedents = parseItems(row.antecedents);
        const consequents = parseItems(row.consequents);
        return {
          key: row.key || `${antecedents.join("|")}=>${consequents.join("|")}`,
          antecedents,
          consequents,
          label: `${antecedents.join(" + ")} -> ${consequents.join(" + ")}`,
          support: Number(row.support || 0),
          confidence: Number(row.confidence || 0),
          lift: Number(row.lift || 0),
          leverage: Number(row.leverage || 0),
          conviction: Number(row.conviction || 0),
          blendScore: Number(row.blend_score || row.score || 0),
        };
      }),
    [rules]
  );

  const filteredRules = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return normalizedRules.filter((rule) => {
      const matchQuery = !keyword || rule.label.toLowerCase().includes(keyword);
      const matchLift = rule.lift >= Number(minLift || 0);
      return matchQuery && matchLift;
    });
  }, [minLift, normalizedRules, query]);

  const availableItems = useMemo(() => {
    const fromCart = Object.keys(recommendations.cart_targets || {});
    if (fromCart.length) {
      return fromCart;
    }

    const items = menuRank.map((row) => row.item);
    if (items.length) {
      return items;
    }

    const set = new Set();
    normalizedRules.forEach((rule) => {
      rule.antecedents.forEach((item) => set.add(item));
      rule.consequents.forEach((item) => set.add(item));
    });
    return [...set];
  }, [menuRank, normalizedRules, recommendations]);

  const suggestions = useMemo(() => {
    const map = recommendations.cart_targets || {};
    if (Array.isArray(map[selectedItem])) {
      return map[selectedItem];
    }

    const picks = [];
    for (const rule of normalizedRules) {
      if (!rule.antecedents.includes(selectedItem)) {
        continue;
      }
      for (const item of rule.consequents) {
        if (item !== selectedItem) {
          picks.push({
            item,
            score: rule.blendScore,
            support: rule.support,
            confidence: rule.confidence,
            lift: rule.lift,
            leverage: rule.leverage,
            conviction: rule.conviction,
            why: `rule signal: confidence ${toPercent(rule.confidence)}, lift ${toFixed(
              rule.lift,
              2
            )}`,
          });
        }
      }
    }
    return picks.sort((left, right) => right.score - left.score).slice(0, 6);
  }, [normalizedRules, recommendations, selectedItem]);

  const portfolio = useMemo(
    () => recommendations.portfolio || {},
    [recommendations]
  );

  const ruleLabel = (rule) => {
    const antecedents = parseItems(rule?.antecedents);
    const consequents = parseItems(rule?.consequents);
    return `${antecedents.join(" + ")} -> ${consequents.join(" + ")}`;
  };

  useEffect(() => {
    if (!availableItems.includes(selectedItem)) {
      setSelectedItem(availableItems[0] || "");
    }
  }, [availableItems, selectedItem]);

  return (
    <section className="page-grid">
      <section className="split-grid">
        <article className="panel">
          <h2>Rule Explorer</h2>
          <div className="control-grid">
            <label className="control">
              Search by item
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                type="text"
                placeholder="e.g. Burger, Fries, Iced Tea"
              />
            </label>
            <label className="control">
              Minimum Lift
              <input
                value={minLift}
                onChange={(event) => setMinLift(Number(event.target.value || 0))}
                type="number"
                step="0.1"
                min="0"
              />
            </label>
          </div>
          <table>
            <thead>
              <tr>
                <th>Rule</th>
                <th>Support</th>
                <th>Confidence</th>
                <th>Lift</th>
                <th>Leverage</th>
                <th>Conviction</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {filteredRules.slice(0, 40).map((rule) => (
                <tr key={rule.key}>
                  <td>{rule.label}</td>
                  <td>{toPercent(rule.support)}</td>
                  <td>{toPercent(rule.confidence)}</td>
                  <td>{toFixed(rule.lift, 2)}</td>
                  <td>{toFixed(rule.leverage, 4)}</td>
                  <td>{toFixed(rule.conviction, 2)}</td>
                  <td>{toFixed(rule.blendScore, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!filteredRules.length ? (
            <p className="muted">No rules matched this filter.</p>
          ) : null}
        </article>

        <article className="panel">
          <h2>Frequently Bought Together Simulator</h2>
          <label className="control">
            Item added to cart
            <select
              value={selectedItem}
              onChange={(event) => setSelectedItem(event.target.value)}
            >
              {availableItems.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <div className="suggestions">
            {suggestions.map((suggestion) => (
              <article key={suggestion.item} className="suggestion-row">
                <h4>{suggestion.item}</h4>
                <p>{suggestion.why}</p>
                <small>
                  support {toPercent(suggestion.support)} | confidence
                  {" "}{toPercent(suggestion.confidence)} | lift
                  {" "}{toFixed(suggestion.lift, 2)}
                </small>
              </article>
            ))}
          </div>
          {!suggestions.length ? (
            <p className="muted">No suggestion for this selected meal.</p>
          ) : null}
        </article>
      </section>

      <article className="panel">
        <h2>Portfolio Movement</h2>
        <div className="portfolio-grid">
          <div className="portfolio-col">
            <h3>Stable</h3>
            <p className="count">{portfolio.stable_count || 0}</p>
            <ul>
              {(portfolio.stable || []).map((rule, index) => (
                <li key={`stable-${index}`}>{ruleLabel(rule)}</li>
              ))}
            </ul>
          </div>
          <div className="portfolio-col">
            <h3>Emerging</h3>
            <p className="count">{portfolio.emerging_count || 0}</p>
            <ul>
              {(portfolio.emerging || []).map((rule, index) => (
                <li key={`emerging-${index}`}>{ruleLabel(rule)}</li>
              ))}
            </ul>
          </div>
          <div className="portfolio-col">
            <h3>Fading</h3>
            <p className="count">{portfolio.fading_count || 0}</p>
            <ul>
              {(portfolio.fading || []).map((rule, index) => (
                <li key={`fading-${index}`}>{ruleLabel(rule)}</li>
              ))}
            </ul>
          </div>
        </div>
      </article>
    </section>
  );
}

export default RulesPage;
