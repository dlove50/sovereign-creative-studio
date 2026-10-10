"use client";

import { useState } from "react";
import { ExternalLink, Search } from "lucide-react";

const TOOLS = [
  ["ChatGPT App", "Create and manage HeyGen videos through ChatGPT.", "https://chatgpt.com/plugins/plugin_asdk_app_69418aad55e08191aa5e437b649ca2e4"],
  ["n8n", "Workflow automation"], ["Autohive", "Personalized video workflows"],
  ["Slack", "Video creation from conversations"], ["HubSpot", "CRM video workflows"],
  ["Vimeo", "Video hosting and distribution"], ["Adobe Express", "Creative editing"],
  ["Canva", "Presentation and design workflows"], ["Tolstoy", "Interactive video players"],
  ["Trupeer", "Screen recordings and voiceovers"], ["FlowShare", "Training and process guides"],
  ["Mindstamp", "Interactive video experiences"], ["Repurpose.io", "Content distribution"],
  ["Zapier", "App automation"], ["Make", "Visual workflow automation"],
  ["Pabbly", "Connected app workflows"], ["Plainly Videos", "Template video production"],
  ["Clay", "Personalized video workflows"], ["Hexus", "Product demonstrations"],
  ["viaSocket", "App workflow automation"],
];

export function IntegrationDirectory() {
  const [query, setQuery] = useState("");
  const shown = TOOLS.filter(([name, detail]) => `${name} ${detail}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="space-y-4" aria-label="Integration directory">
    <div><h2 className="text-xl font-semibold">Apps and workflow integrations</h2>
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">Explore HeyGen’s connected tools. These links open external setup pages; they do not install a connector in Sovereign. Sovereign’s direct API connections are configured above.</p></div>
    <label className="flex items-center gap-2 rounded-xl border border-border px-3 py-2">
      <Search className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      <input aria-label="Search integrations" placeholder="Search integrations" value={query} onChange={e => setQuery(e.target.value)} className="w-full bg-transparent text-sm focus:outline-none" />
    </label>
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{shown.map(([name, detail, url]) => <li key={name}>
      <a href={url || "https://app.heygen.com/apps/integrations"} target="_blank" rel="noopener noreferrer" className="block h-full rounded-xl border border-border bg-card p-4 hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span className="flex items-center justify-between gap-2 font-semibold">{name}<ExternalLink className="h-4 w-4" aria-hidden="true" /></span>
        <span className="mt-2 block text-sm text-muted-foreground">{detail}</span>
        <span className="mt-3 block text-xs text-muted-foreground">{url ? "Open ChatGPT plugin setup" : "View in HeyGen’s integration directory"}</span>
      </a>
    </li>)}</ul>
    {!shown.length ? <p className="text-sm text-muted-foreground">No integrations match your search.</p> : null}
  </section>;
}
