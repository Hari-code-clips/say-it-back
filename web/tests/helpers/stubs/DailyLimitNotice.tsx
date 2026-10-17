// Test stand-in for src/shell/DailyLimitNotice.tsx: the real one reads an external store with no server snapshot, which
// react-dom/server refuses. Not reached = nothing shown, which is the state every screen test wants.
export function DailyLimitNotice() {
  return null
}
