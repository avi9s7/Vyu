import { PlaceholderSurface } from "@/components/domain/PlaceholderSurface";

export default function NewSearchPage() {
  return (
    <PlaceholderSurface
      title="New Search"
      description="Submit a governed research question and define transparent evidence scope before job creation."
      items={[
        "Research question input",
        "Source selection",
        "Date range",
        "Evidence type filters",
        "Population / intervention / comparator fields",
        "Only-approved-sources toggle",
        "Search Scope Summary",
        "Recent Searches limited to 2 items"
      ]}
    />
  );
}
