import type { LandingPageLocation } from "../../lib/seo/landingPage";

export const nearPgLandingLocations = [
  {
    name: "ITPL",
    city: "Bengaluru",
    locality: "Whitefield",
    type: "tech-park",
  },
  {
    name: "Ecospace",
    city: "Bengaluru",
    locality: "Bellandur",
    type: "business-park",
  },
  {
    name: "Ecoworld",
    city: "Bengaluru",
    locality: "Bellandur",
    type: "business-park",
  },
  {
    name: "Embassy Tech Village",
    city: "Bengaluru",
    locality: "Outer Ring Road",
    type: "tech-park",
  },
  {
    name: "Bagmane",
    city: "Bengaluru",
    locality: "CV Raman Nagar",
    type: "tech-park",
  },
  {
    name: "Manyata",
    city: "Bengaluru",
    locality: "Nagavara",
    type: "tech-park",
  },
] as const satisfies readonly LandingPageLocation[];
