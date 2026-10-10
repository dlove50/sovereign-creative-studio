// Options and prompt builder for the "Design with AI" avatar form. Pure, so it is easy to test.

export const AGES = ["Child", "Teen", "Young adult", "Adult", "Middle-aged", "Senior"] as const;
export const GENDERS = ["Man", "Woman", "Non-binary"] as const;
export const ETHNICITIES = [
  "Not specified", "Black", "White", "East Asian", "South Asian", "Southeast Asian", "Hispanic or Latino",
  "Middle Eastern", "Indigenous", "Pacific Islander", "Mixed",
] as const;
export const ORIENTATIONS = ["Landscape", "Portrait", "Square"] as const;
export const POSES = ["Full body", "Upper body", "Face"] as const;
export const STYLES = [
  "Unspecified", "Realistic", "Pixar style", "Disney-style 2D", "Cinematic", "Vintage", "Noir", "Cyberpunk",
  "Anime", "Cartoon", "Watercolor", "Claymation", "Stop-motion",
] as const;

export type DesignForm = {
  name: string;
  age: (typeof AGES)[number];
  gender: (typeof GENDERS)[number];
  ethnicity: (typeof ETHNICITIES)[number];
  description: string;
  orientation: (typeof ORIENTATIONS)[number];
  pose: (typeof POSES)[number];
  style: (typeof STYLES)[number];
};

export const EMPTY_DESIGN: DesignForm = {
  name: "", age: "Adult", gender: "Man", ethnicity: "Not specified", description: "",
  orientation: "Portrait", pose: "Upper body", style: "Unspecified",
};

export const SAMPLE_DESCRIPTIONS = [
  "warm smile, short curly hair, navy blazer over a light blue shirt, friendly and confident",
  "calm manner, round glasses, grey cardigan, soft natural makeup, speaks like a kind teacher",
  "athletic build, faded haircut, plain white t-shirt, relaxed and approachable",
  "silver hair, neat beard, dark turtleneck, thoughtful expression like a documentary narrator",
];

const POSE_PHRASE: Record<DesignForm["pose"], string> = {
  "Full body": "Full-body standing portrait",
  "Upper body": "Waist-up portrait",
  Face: "Head-and-shoulders close-up portrait",
};

const STYLE_PHRASE: Record<DesignForm["style"], string> = {
  Unspecified: "",
  Realistic: "photorealistic, soft natural light",
  "Disney-style 2D": "Disney-style hand-drawn 2D animated character, expressive features, graceful shapes, richly painted colors",
  Vintage: "vintage portrait photography, warm faded colors, subtle film grain, nostalgic styling",
  Noir: "black-and-white film noir portrait, dramatic chiaroscuro lighting, deep shadows, classic cinematic atmosphere",
  Cyberpunk: "cyberpunk character portrait, neon cyan and magenta lighting, futuristic clothing, high-tech details",
  Claymation: "handcrafted clay animation character, sculpted clay texture, rounded expressive features, miniature studio lighting",
  "Stop-motion": "stop-motion puppet character, tactile fabric and felt textures, handcrafted miniature details, cinematic studio lighting",
  "Pixar style": "Pixar-style 3D animated character, smooth stylised render, expressive eyes",
  Anime: "anime illustration, clean line art, soft cel shading",
  Cartoon: "friendly cartoon character, bold shapes, flat colours",
  Watercolor: "watercolor painting, soft washes of colour",
  Cinematic: "cinematic film still, shallow depth of field, dramatic lighting",
};

const COMPOSITION: Record<DesignForm["orientation"], string> = {
  Landscape: "wide horizontal framing",
  Portrait: "tall vertical framing",
  Square: "square framing",
};

export function buildAvatarPrompt(form: DesignForm): string {
  const who = [form.age.toLowerCase(), form.ethnicity === "Not specified" ? "" : form.ethnicity, form.gender.toLowerCase()]
    .filter(Boolean)
    .join(" ");
  const parts = [
    `${POSE_PHRASE[form.pose]} of a ${who}`,
    form.description.trim(),
    STYLE_PHRASE[form.style],
    "facing the camera, mouth closed, plain studio background",
    COMPOSITION[form.orientation],
  ];
  return parts.filter(Boolean).join(", ");
}

export function isDesignReady(form: DesignForm): boolean {
  return form.name.trim().length > 0 && form.description.trim().length > 0;
}
