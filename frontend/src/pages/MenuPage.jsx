import { useMemo } from "react";

const menuGroups = [
  {
    title: "Rice Meals",
    subtitle: "Heavy and filling",
    items: [
      { name: "Chicken Rice", price: 99 },
      { name: "Sisig Rice", price: 109 },
      { name: "Spaghetti", price: 85 },
      { name: "Extra Rice", price: 25 },
    ],
  },
  {
    title: "Burgers and Snacks",
    subtitle: "Quick picks for students",
    items: [
      { name: "Burger", price: 65 },
      { name: "Hotdog", price: 55 },
      { name: "Nuggets", price: 79 },
      { name: "Fries", price: 59 },
      { name: "Cheese Stick", price: 69 },
      { name: "Lumpia", price: 49 },
    ],
  },
  {
    title: "Drinks and Sweets",
    subtitle: "Add-on boosters",
    items: [
      { name: "Iced Tea", price: 39 },
      { name: "Soda", price: 35 },
      { name: "Water", price: 25 },
      { name: "Coffee", price: 45 },
      { name: "Sundae", price: 49 },
      { name: "Donut", price: 39 },
      { name: "Extra Sauce", price: 15 },
    ],
  },
];

function MenuPage({ recommendations = {}, topMeals = [], menuRank = [] }) {
  const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
  const toFixed = (value, digits = 2) => Number(value || 0).toFixed(digits);

  const topMealSet = useMemo(
    () => new Set(topMeals.slice(0, 6).map((row) => row.item)),
    [topMeals]
  );

  const homepageTopSet = useMemo(
    () => new Set(menuRank.slice(0, 6).map((row) => row.item)),
    [menuRank]
  );

  const comboRows = useMemo(
    () => (recommendations.top_bundles || []).slice(0, 5),
    [recommendations]
  );

  const isTopMeal = (item) => topMealSet.has(item);
  const isHomepageTop = (item) => homepageTopSet.has(item);

  return (
    <section className="page-grid">
      <article className="panel hero">
        <div className="hero-copy">
          <p className="eyebrow">Food Stall Catalog</p>
          <h2>ComboBravo Menu</h2>
          <p>
            Student-friendly meals with smart combo suggestions. Labels below are
            powered by your current dataset rankings.
          </p>
        </div>
        <div className="hero-badges">
          <span>{topMeals.length} Ranked Items</span>
          <span>{recommendations.promos?.length || 0} Promo Ideas</span>
          <span>{recommendations.system_metrics?.n_rules_blended || 0} Active Rules</span>
        </div>
      </article>

      <section className="menu-grid">
        {menuGroups.map((group) => (
          <article key={group.title} className="panel menu-card">
            <h3>{group.title}</h3>
            <p className="muted">{group.subtitle}</p>
            <div className="items">
              {group.items.map((item) => (
                <article key={item.name} className="item-row">
                  <div>
                    <h4>{item.name}</h4>
                    <div className="tags">
                      {isTopMeal(item.name) ? <span className="tag top">Top Seller</span> : null}
                      {isHomepageTop(item.name) ? (
                        <span className="tag rank">Homepage Pick</span>
                      ) : null}
                    </div>
                  </div>
                  <p className="price">PHP {item.price.toFixed(2)}</p>
                </article>
              ))}
            </div>
          </article>
        ))}
      </section>

      <section className="split-grid">
        <article className="panel">
          <h3>Recommended Combos</h3>
          <div className="combo-list">
            {comboRows.map((bundle, index) => (
              <article key={`combo-${index}`} className="combo-row">
                <h4>{(bundle.items || []).join(" + ")}</h4>
                <p>{bundle.why}</p>
                <small>
                  support {toPercent(bundle.support)} | confidence {toPercent(bundle.confidence)}
                  | lift {toFixed(bundle.lift, 2)}
                </small>
              </article>
            ))}
          </div>
          {!comboRows.length ? (
            <p className="muted">No combo recommendations yet.</p>
          ) : null}
        </article>

        <article className="panel">
          <h3>Promo Board</h3>
          <div className="promo-list">
            {(recommendations.promos || []).map((promo, index) => (
              <article key={`promo-${index}`} className="promo-row">
                <p className="promo-name">{promo.promo}</p>
                <p>{(promo.bundle || []).join(" + ")}</p>
                <small>{promo.why}</small>
              </article>
            ))}
          </div>
          {!((recommendations.promos || []).length) ? (
            <p className="muted">No promos available.</p>
          ) : null}
        </article>
      </section>
    </section>
  );
}

export default MenuPage;
