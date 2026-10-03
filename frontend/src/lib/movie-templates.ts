// Starter scene sets for the video editor. They are plain scripts with [brackets] to fill in,
// written for this studio. Each scene stays well under the 1,500 character scene limit.

export const MOVIE_TEMPLATE_CATEGORIES = ["Training", "Corporate", "Marketing", "Sales", "Tutorials", "Real estate", "Finance"] as const;
export type MovieTemplateCategory = (typeof MOVIE_TEMPLATE_CATEGORIES)[number];

export type MovieTemplate = {
  id: string;
  title: string;
  category: MovieTemplateCategory;
  blurb: string;
  scenes: string[];
};

export const MOVIE_TEMPLATES: MovieTemplate[] = [
  { id: "welcome-onboarding", title: "Welcome and onboarding", category: "Training", blurb: "Greet a new team member and set up their first week.",
    scenes: [
      "Welcome to [company]. I'm [name], and I'm glad you're here. Over the next few minutes I'll show you how your first week works.",
      "On day one you'll meet your team, get your accounts set up, and walk through the tools you'll use every day. Nobody expects you to remember it all.",
      "If you get stuck, ask. Your first point of contact is [person]. Welcome aboard, and let's get started.",
    ] },
  { id: "safety-reminder", title: "Safety reminder", category: "Training", blurb: "A short, clear reminder before a shift or site visit.",
    scenes: [
      "Before we start, a quick safety reminder. It takes one minute and it matters every single day.",
      "First, [rule one]. Second, [rule two]. Third, if something looks wrong, stop and tell [person] straight away.",
      "Thank you for looking out for each other. Stay safe, and let's have a good day.",
    ] },
  { id: "quarterly-update", title: "Quarterly update", category: "Corporate", blurb: "Results, what changed, and what's next.",
    scenes: [
      "Hello everyone. Here's a short look at how [quarter] went for [company].",
      "The headline: [main result]. That came from [reason one] and [reason two]. I want to thank everyone who made it happen.",
      "Next quarter we're focused on [priority one] and [priority two]. I'll share more soon. Thanks for watching.",
    ] },
  { id: "announcement", title: "Team announcement", category: "Corporate", blurb: "One clear message to the whole team.",
    scenes: [
      "I have an announcement for the team, and I wanted you to hear it from me directly.",
      "[The news in two or three sentences.] Here's what it means for you: [impact].",
      "If you have questions, send them to [contact]. Thank you for your trust and your hard work.",
    ] },
  { id: "product-launch", title: "Product launch", category: "Marketing", blurb: "Introduce what it is, who it helps, how to get it.",
    scenes: [
      "Meet [product]. It's built for [who], so they can [main benefit] without [pain point].",
      "Here's how it works. [Step one.] [Step two.] [Step three.] It really is that simple.",
      "[Product] is available now at [where]. Try it today, and tell us what you think.",
    ] },
  { id: "special-offer", title: "Limited-time offer", category: "Marketing", blurb: "A short promo with a clear call to action.",
    scenes: [
      "For a limited time, [company] is offering [offer] on [product or service].",
      "That means [specific saving or bonus]. It ends on [date], so don't wait.",
      "Visit [where] or call [number] to claim it. We'd love to work with you.",
    ] },
  { id: "cold-outreach", title: "Friendly introduction", category: "Sales", blurb: "A personal first message to a new contact.",
    scenes: [
      "Hi [name], I'm [your name] from [company]. I noticed [something specific about them], and I thought of you.",
      "We help [type of customer] to [result]. For example, [short proof or example].",
      "If that sounds useful, I'd love a quick chat. You can reach me at [contact]. Thanks for your time.",
    ] },
  { id: "follow-up", title: "Follow-up after a meeting", category: "Sales", blurb: "Recap what you discussed and the next step.",
    scenes: [
      "Hi [name], thank you for meeting with me on [day]. I enjoyed learning about [their goal].",
      "To recap: you want [goal], and the main concern is [concern]. Here's what I suggest: [recommendation].",
      "The next step is [action] by [date]. Let me know if anything changes. Talk soon.",
    ] },
  { id: "how-to-3-steps", title: "How to, in three steps", category: "Tutorials", blurb: "Teach one practical skill clearly.",
    scenes: [
      "Today I'll show you how to [do the thing]. It takes about [time] and you only need [tools].",
      "Step one: [action]. Step two: [action]. Step three: [action]. Take your time with the second step, because that's where most people slip.",
      "That's it. You've just [achieved result]. If this helped, try [next idea] next.",
    ] },
  { id: "explainer", title: "One big idea, explained", category: "Tutorials", blurb: "Explain a concept with an everyday example.",
    scenes: [
      "Have you ever wondered [question]? Let me explain it simply.",
      "Think of it like [everyday comparison]. In the same way, [concept] works by [short explanation].",
      "The key takeaway: [one sentence]. Now you can [what they can do with it].",
    ] },
  { id: "listing-spotlight", title: "Listing spotlight", category: "Real estate", blurb: "Present a home and its best features.",
    scenes: [
      "Welcome to [address]. This [type of home] offers [bedrooms] bedrooms, [bathrooms] bathrooms, and [size] of living space.",
      "Inside, you'll find [feature one], [feature two], and [feature three]. Outside, there's [outdoor feature] and easy access to [neighbourhood highlight].",
      "It's listed at [price]. To book a viewing, contact [agent] at [contact].",
    ] },
  { id: "market-update", title: "Market update", category: "Finance", blurb: "A calm, factual summary of the period.",
    scenes: [
      "Here's your [weekly or monthly] market update from [company]. This is general information, not personal advice.",
      "Over the period, [market or sector] moved [direction], mainly because of [reason]. [Second point.]",
      "Looking ahead, keep an eye on [event or data]. For questions about your own situation, speak with [adviser or contact].",
    ] },
];
