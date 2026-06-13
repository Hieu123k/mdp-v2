import { redirect } from "next/navigation";

// prompt 05: the Streaming tab was merged into Migration Jobs (per-row ⚙ → streaming drawer, reusing
// StreamingEditor). This route now redirects so any old bookmark/link lands on the new home instead
// of 404-ing. StreamingEditor itself lives on and renders inside the Migration Jobs drawer.
export default function StreamingPage() {
  redirect("/migration-jobs");
}
