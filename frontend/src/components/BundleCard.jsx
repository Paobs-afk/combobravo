function BundleCard({ bundle, index = 1 }) {
  const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
  const toFloat = (value, digits = 2) => Number(value || 0).toFixed(digits);

  return (
    <article className="bundle-card">
      <div className="bundle-top">
        <p className="bundle-id">Bundle {index}</p>
        <h3>{bundle.name}</h3>
      </div>
      <div className="bundle-items">
        {(bundle.items || []).map((item) => (
          <span key={item} className="tag">
            {item}
          </span>
        ))}
      </div>
      <p className="bundle-why">{bundle.why}</p>
      <div className="metrics">
        <span>Support {toPercent(bundle.support)}</span>
        <span>Confidence {toPercent(bundle.confidence)}</span>
        <span className="lift">Lift {toFloat(bundle.lift)}x</span>
        <span>Leverage {toFloat(bundle.leverage, 4)}</span>
        <span>Conviction {toFloat(bundle.conviction, 2)}</span>
      </div>
    </article>
  );
}

export default BundleCard;
