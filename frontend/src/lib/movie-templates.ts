// Starter scene sets for the video editor. They are plain scripts with [brackets] to fill in,
// written for this studio. Each scene stays well under the 1,500 character scene limit.

export const MOVIE_TEMPLATE_CATEGORIES = ["Training", "Corporate", "Marketing", "Sales", "Tutorials & Explainers", "Learning & Development", "Explainer Video", "Real estate", "Finance"] as const;
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
  { id: "how-to-3-steps", title: "How to, in three steps", category: "Tutorials & Explainers", blurb: "Teach one practical skill clearly.",
    scenes: [
      "Today I'll show you how to [do the thing]. It takes about [time] and you only need [tools].",
      "Step one: [action]. Step two: [action]. Step three: [action]. Take your time with the second step, because that's where most people slip.",
      "That's it. You've just [achieved result]. If this helped, try [next idea] next.",
    ] },
  { id: "explainer", title: "One big idea, explained", category: "Explainer Video", blurb: "Explain a concept with an everyday example.",
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
  { id: "course-overview", title: "Course overview", category: "Learning & Development", blurb: "Explain the learning goal, structure and preparation.",
    scenes: [
      "Welcome to [course]. By the end, you will be able to [observable skill]. This course is designed for [learners] who already know [starting knowledge].",
      "We will start with [foundation], work through [example], and finish with [practice task]. Set aside [time] and have [materials] ready.",
      "Your final task is [assessment]. Use [success criteria] to check your work. Start the first lesson when you are ready, and ask questions through [support channel].",
    ] },
  { id: "lesson-and-practice", title: "Lesson and practice", category: "Learning & Development", blurb: "Teach a skill, invite practice and check understanding.",
    scenes: [
      "In this lesson, we will practice [skill]. It helps when [situation]. Watch for [important detail] as we work through an example.",
      "Start by [first action]. Then [next action]. In our example, [input] produces [result] because [reason].",
      "Now try [practice task] yourself. Pause here before continuing. Compare your result with [expected result], and check [common mistake] if yours differs.",
      "You are ready to move on when you can [success criterion] without help. Next, we will apply this skill to [next topic].",
    ] },
  { id: "knowledge-base-answer", title: "Knowledge base answer", category: "Tutorials & Explainers", blurb: "Resolve a common question with a clear escalation path.",
    scenes: [
      "If you are seeing [symptom], this guide will help you check [likely cause]. It applies to [product version or situation].",
      "First, confirm [prerequisite]. Open [location], choose [setting], and enter [value]. You should see [confirmation].",
      "If the issue continues, note [diagnostic detail] and contact [support]. Include [useful information] so the team can help without repeating these steps.",
    ] },
  { id: "product-walkthrough", title: "Product walkthrough", category: "Tutorials & Explainers", blurb: "Show a practical workflow from setup to saved result.",
    scenes: [
      "Let's use [product] to complete [task]. Before you begin, sign in and have [required input] ready.",
      "From [starting screen], select [control]. Add [input], choose [option], and review [preview or confirmation] before continuing.",
      "Select [finish action] to save your result. Find it under [location]. Check [quality criterion], then use [sharing or export action] if you need a copy.",
    ] },
  { id: "business-strategy", title: "Business strategy briefing", category: "Corporate", blurb: "Connect a goal to choices, owners and review dates.",
    scenes: [
      "Our goal for [period] is [measurable outcome]. The evidence behind this priority is [customer need or operational finding].",
      "We will focus on [initiative one] and [initiative two]. We are postponing [other work] so the team has the time and resources to deliver.",
      "[Owner] will lead [milestone] by [date]. We will review [metric] at [cadence] and adjust if [decision threshold] is reached.",
    ] },
  { id: "hiring-role-overview", title: "Hiring role overview", category: "Corporate", blurb: "Describe the work, selection process and application route.",
    scenes: [
      "We are hiring a [role] for [team]. You will help [purpose] by working on [main responsibilities].",
      "The role requires [essential skills]. Experience with [optional skill] is helpful. The working arrangement is [location and schedule], with [published compensation or benefits information].",
      "Apply through [application route] by [date]. The process includes [selection stages]. For accessibility arrangements or questions, contact [contact].",
    ] },
  { id: "sales-report", title: "Sales results report", category: "Sales", blurb: "Separate measured results from forecasts and next actions.",
    scenes: [
      "Here are the sales results for [period], using data updated on [date]. Actual revenue was [amount], compared with a target of [target].",
      "[Segment] contributed [result]. The main change came from [supported explanation]. Our pipeline forecast is [forecast], which remains an estimate based on [assumptions].",
      "Next, [owner] will address [action] by [date]. We will track [metric] and review progress at [next meeting].",
    ] },
  { id: "financial-planning-explainer", title: "Financial planning basics", category: "Explainer Video", blurb: "Explain goals, cash flow and review habits without product recommendations.",
    scenes: [
      "A financial plan connects your goals with the money coming in and going out. Start by naming a goal, its estimated cost, and when you want to reach it.",
      "List income, essential spending, debt payments and existing savings. The amount left over helps you understand what may be available for your goal. Use your own figures and check that they are current.",
      "Consider how unexpected costs or changes in income could affect the plan. Review it when your circumstances change. For decisions involving investments, taxes or borrowing, discuss your situation with a qualified professional.",
    ] },
];
