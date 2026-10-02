// Look templates for the Look studio. Each variant becomes one Qwen image edit of
// the user's photo; a Look Pack has several variants and makes them all at once.
// Cover images are generated locally (tools: see docs) and live in /public.

export const LOOK_CATEGORIES = [
  "Studio", "Office", "Presentation", "Fitness", "Automotive",
  "Construction", "Real Estate", "Medical", "Home",
] as const;
export type LookCategory = (typeof LOOK_CATEGORIES)[number];

export type LookVariant = { label: string; prompt: string };
export type LookTemplate = {
  id: string;
  name: string;
  category: LookCategory;
  cover: string;
  coverPrompt: string; // used once to generate the cover image
  variants: LookVariant[];
};

export const KEEP_IDENTITY =
  "Keep the exact same person, same face, same identity, same skin tone and hairstyle. " +
  "Waist-up portrait facing the camera, mouth closed, natural light, photorealistic.";

const cover = (id: string) => `/sovereign-ui/looks/${id}.webp`;

export const LOOK_TEMPLATES: LookTemplate[] = [
  {
    id: "creator-studio", name: "Creator studio", category: "Studio", cover: cover("creator-studio"),
    coverPrompt: "Waist-up photo of a smiling man in a light grey hoodie at a desk with a podcast microphone on a boom arm, home studio with shelves and teal accent lights behind him, photorealistic",
    variants: [
      { label: "Hoodie at the podcast mic", prompt: "Change the outfit to a light grey hoodie, add a podcast microphone on a boom arm in front of them, and place them in a cozy home studio with shelves and soft teal accent lights." },
      { label: "Black sweater, warm studio", prompt: "Change the outfit to a black crew-neck sweater and place them in a warm home studio with fairy lights and bookshelves." },
      { label: "Casual shirt, bright loft", prompt: "Change the outfit to a relaxed denim shirt and place them in a bright loft office with plants and large windows." },
    ],
  },
  {
    id: "corporate", name: "Corporate", category: "Office", cover: cover("corporate"),
    coverPrompt: "Waist-up photo of a confident Black woman in a navy suit and white blouse in a bright glass office with city view, photorealistic corporate portrait",
    variants: [
      { label: "Navy suit, glass office", prompt: "Change the outfit to a tailored navy suit with a white shirt and place them in a bright glass-walled office with a city view." },
      { label: "Charcoal suit, boardroom", prompt: "Change the outfit to a charcoal suit with an open collar and place them in a modern boardroom with a long table." },
      { label: "Blazer at the standing desk", prompt: "Change the outfit to a smart blazer over a plain tee and place them beside a standing desk in an open-plan office." },
      { label: "Skyline window", prompt: "Change the outfit to a dark suit and place them in front of a large window overlooking a city skyline on a clear day." },
    ],
  },
  {
    id: "slate", name: "Slate tech", category: "Studio", cover: cover("slate"),
    coverPrompt: "Waist-up photo of a man in a dark zip-neck sweater against a deep blue studio backdrop with soft side light, minimal tech presenter, photorealistic",
    variants: [
      { label: "Zip sweater, blue backdrop", prompt: "Change the outfit to a dark zip-neck sweater and place them against a deep slate-blue studio backdrop with soft side light." },
      { label: "Black tee, dark studio", prompt: "Change the outfit to a fitted black t-shirt and place them in a dark studio with a single soft key light." },
    ],
  },
  {
    id: "professor", name: "Professor", category: "Presentation", cover: cover("professor"),
    coverPrompt: "Waist-up photo of a friendly older South Asian professor in a tweed blazer seated in a wood-paneled library with a desk lamp, photorealistic",
    variants: [
      { label: "Tweed blazer, library", prompt: "Change the outfit to a tweed blazer over a light shirt and place them in a wood-paneled library with a warm desk lamp." },
      { label: "Cardigan, lecture hall", prompt: "Change the outfit to a knit cardigan and place them at the front of a university lecture hall." },
      { label: "Glasses, book stacks", prompt: "Change the outfit to a navy blazer and add thin glasses, placing them between tall library book stacks." },
    ],
  },
  {
    id: "presenter", name: "Presenter", category: "Presentation", cover: cover("presenter"),
    coverPrompt: "Waist-up photo of a woman with curly hair in a beige blazer on a conference stage with a soft blue projector glow behind her, photorealistic",
    variants: [
      { label: "Beige blazer on stage", prompt: "Change the outfit to a beige blazer over a white shirt and place them on a conference stage with a soft blue projector glow behind them." },
      { label: "Navy blazer, keynote", prompt: "Change the outfit to a navy blazer with a white tee and place them on a dark keynote stage with spotlights." },
    ],
  },
  {
    id: "coastal", name: "Coastal linen", category: "Home", cover: cover("coastal"),
    coverPrompt: "Waist-up photo of a relaxed woman in a white linen shirt in a bright airy beach house with sheer curtains, photorealistic",
    variants: [
      { label: "White linen, beach house", prompt: "Change the outfit to a white linen shirt and place them in a bright, airy beach house with sheer curtains." },
      { label: "Linen on the porch", prompt: "Change the outfit to a sand-colored linen shirt and place them on a sunny wooden porch with the ocean in the distance." },
    ],
  },
  {
    id: "fitness", name: "Fitness", category: "Fitness", cover: cover("fitness"),
    coverPrompt: "Waist-up photo of a fit Latina woman in a black athletic t-shirt in a bright kitchen with fresh vegetables on the counter, photorealistic",
    variants: [
      { label: "Athletic tee, healthy kitchen", prompt: "Change the outfit to a black athletic t-shirt and place them in a bright kitchen with fresh vegetables on the counter." },
      { label: "Training at the gym", prompt: "Change the outfit to a fitted training top and place them in a modern gym with weights and machines behind them." },
    ],
  },
  {
    id: "construction", name: "Construction", category: "Construction", cover: cover("construction"),
    coverPrompt: "Waist-up photo of a construction manager wearing a white hard hat and a bright yellow hi-vis vest at a building site with cranes, photorealistic",
    variants: [
      { label: "Hard hat on site", prompt: "Give them a white hard hat and a bright yellow hi-vis vest over a work shirt, and place them at a building site with cranes behind them." },
      { label: "Industrial plant", prompt: "Give them a white hard hat and an orange-and-navy work jacket, and place them inside a clean industrial plant with machinery." },
    ],
  },
  {
    id: "automotive", name: "Automotive", category: "Automotive", cover: cover("automotive"),
    coverPrompt: "Waist-up photo of a mechanic in navy coveralls in a clean auto repair garage with a car on a lift behind him, photorealistic",
    variants: [
      { label: "Mechanic in the garage", prompt: "Change the outfit to navy work coveralls and place them in a clean auto repair garage with a car raised on a lift behind them." },
      { label: "Dealership showroom", prompt: "Change the outfit to a navy blazer with an open-collar shirt and place them in a bright car dealership showroom." },
    ],
  },
  {
    id: "real-estate", name: "Real estate", category: "Real Estate", cover: cover("real-estate"),
    coverPrompt: "Waist-up photo of a Black man real estate agent in a navy blazer standing in front of a suburban house with a for-sale sign on the lawn, photorealistic",
    variants: [
      { label: "In front of the listing", prompt: "Change the outfit to a navy blazer with an open-collar shirt and place them in front of a suburban house with a for-sale sign on the lawn." },
      { label: "Modern kitchen tour", prompt: "Change the outfit to a smart casual sweater and place them in a bright modern kitchen of a home for sale." },
    ],
  },
  {
    id: "medical", name: "Healthcare", category: "Medical", cover: cover("medical"),
    coverPrompt: "Waist-up photo of an East Asian woman doctor in a white coat over navy scrubs in a bright clinic examination room, photorealistic",
    variants: [
      { label: "White coat, clinic", prompt: "Change the outfit to a white doctor's coat over navy scrubs and place them in a bright clinic examination room." },
      { label: "Scrubs, hospital hallway", prompt: "Change the outfit to teal medical scrubs and place them in a calm, well-lit hospital hallway." },
    ],
  },
  {
    id: "cozy", name: "Cozy knits", category: "Home", cover: cover("cozy"),
    coverPrompt: "Waist-up photo of an East Asian man in a cream turtleneck sweater in a warm wood-paneled living room at golden hour, photorealistic",
    variants: [
      { label: "Turtleneck, living room", prompt: "Change the outfit to a cream turtleneck sweater and place them in a warm wood-paneled living room at golden hour." },
      { label: "Cardigan by the window", prompt: "Change the outfit to a chunky knit cardigan and place them beside a rainy window in a cozy room with a lamp." },
    ],
  },
  {
    id: "minimal", name: "Clean white", category: "Studio", cover: cover("minimal"),
    coverPrompt: "Waist-up photo of a woman with short dark hair in a black blazer and white shirt against a seamless white studio background, crisp fashion portrait, photorealistic",
    variants: [
      { label: "Black blazer on white", prompt: "Change the outfit to a black blazer over a white shirt and place them against a seamless white studio background." },
    ],
  },
  {
    id: "law", name: "Law office", category: "Office", cover: cover("law"),
    coverPrompt: "Waist-up photo of a lawyer in a dark suit and tie in front of shelves of leather-bound law books, photorealistic",
    variants: [
      { label: "Suit and tie, law books", prompt: "Change the outfit to a dark suit with a tie and place them in front of shelves of leather-bound law books." },
    ],
  },
  {
    id: "warm-earthy", name: "Warm earthy", category: "Studio", cover: cover("warm-earthy"),
    coverPrompt: "Waist-up photo of a man in a rust-orange knit sweater against a warm terracotta backdrop with soft sunlight, photorealistic",
    variants: [
      { label: "Rust sweater, warm light", prompt: "Change the outfit to a rust-orange knit sweater and place them against a warm terracotta backdrop with soft sunlight." },
    ],
  },
];

export const isPack = (t: LookTemplate) => t.variants.length > 1;
export const MIN_CUSTOM_PACK = 3;
export const MAX_CUSTOM_PACK = 12;
