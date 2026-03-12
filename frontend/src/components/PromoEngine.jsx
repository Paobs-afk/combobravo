function PromoEngine({ promos = [] }) {
  if (!promos.length) {
    return (
      <section className="promo-engine">
        <article className="promo-empty">
          No promo candidate for this iteration. Try another dataset/iteration.
        </article>
      </section>
    );
  }

  return (
    <section className="promo-engine">
      {promos.map((promo, index) => (
        <article key={`${promo.promo}-${index}`} className="promo-item">
          <div className="promo-head">
            <p className="promo-tag">{promo.promo}</p>
          </div>
          <p className="promo-bundle">{(promo.bundle || []).join(" + ")}</p>
          <p className="promo-logic">{promo.why}</p>
        </article>
      ))}
    </section>
  );
}

export default PromoEngine;
