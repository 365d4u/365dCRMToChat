// A presentation mapping uses reviewed ownership, independent of profile churn.
export function eligibleReference(row, lastIdentityChange) {
  if (!row.referenceReviewedAt || !row.rootReviewedAt) return false;
  const reviewed=Math.min(new Date(row.referenceReviewedAt).getTime(),new Date(row.rootReviewedAt).getTime());
  if (!Number.isFinite(reviewed) || (lastIdentityChange!==undefined &&
      (!Number.isFinite(lastIdentityChange) || lastIdentityChange>=reviewed))) return false;
  const current=row.referenceVersion===row.customerVersion && row.rootVersion===row.customerVersion;
  return current || row.reviewedEvidence===true;
}
