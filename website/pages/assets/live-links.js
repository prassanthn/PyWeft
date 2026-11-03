// The live apps (live/...) open in a tab of their own, where they have the
// whole window. Links in pages say so themselves; this covers the menu,
// which mkdocs renders without a target.
document$.subscribe(() => {
  for (const link of document.querySelectorAll('a[href*="live/"]')) {
    link.target = "_blank";
  }
});
