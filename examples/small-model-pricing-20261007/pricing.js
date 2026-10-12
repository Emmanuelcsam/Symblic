function renderPricing() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pricing Plans</title>
  <style>${pricingCSS()}</style>
</head>
<body>
  <main>
    <h1>Pricing Plans</h1>
    <div class="grid">
      ${renderPlan("Basic","$0")}
      ${renderPlan("Studio","$12")}
      ${renderPlan("Team","$30")}
    </div>
  </main>
</body>
</html>`;
}