"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, assetUrl } from "@/lib/api";
import type { BrandVisuals } from "@/lib/types";

export function BrandVisualsView({ projectId }: { projectId: string }) {
  const [spec, setSpec] = useState<BrandVisuals | null>(null);
  const [name, setName] = useState("Brand visuals");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [website, setWebsite] = useState("");
  // URL-fetching state
  const [fetchUrl, setFetchUrl] = useState<Map<string, string>>(new Map());
  const [fetchBusy, setFetchBusy] = useState(false);
  useEffect(() => {
    Promise.all([api.getBrandVisuals(projectId), api.listProjects()]).then(([visuals, projects]) => { setSpec(visuals); setName(projects.find(p=>p.id===projectId)?.name || "Brand visuals"); }).catch(e => setError(e.message || "Could not load the brand."));
  }, [projectId]);
  async function save() {
    if (!spec) return;
    setBusy(true); setError(""); setMessage("");
    try { setSpec(await api.updateBrandVisuals(projectId, spec)); setDirty(false); setMessage("Visual settings saved."); }
    catch(e) { setError(e instanceof Error ? e.message : "Could not save the visual settings."); }
    finally { setBusy(false); }
  }
  async function importWebsite() {
    if (busy || dirty || !website.trim()) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const updated = await api.importBrandWebsite(projectId, website.trim());
      setSpec(updated);
      setMessage(`Imported and saved ${updated.imported_colors} new colors and ${updated.imported_fonts} font preferences. Review the results below.`);
    } catch(e) { setError(e instanceof Error ? e.message : "Could not import this website."); }
    finally { setBusy(false); }
  }
  async function upload(kind: "logos" | "assets", file?: File) {
    if (!file || !spec) return;
    setBusy(true); setError(""); setMessage("");
    try { const updated = await api.uploadBrandImage(projectId, kind, file); setSpec(current => current ? {...current, logos:updated.logos, assets:updated.assets} : updated); setMessage("Image uploaded and saved."); }
    catch(e) { setError(e instanceof Error ? e.message : "Could not upload the image."); }
    finally { setBusy(false); }
  }

  function toggleFetchUrl(kind: "logos" | "assets") {
    const key = kind;
    const urlMap = new Map(fetchUrl);
    if (urlMap.has(key)) urlMap.delete(key);
    else urlMap.set(key, "");
    setFetchUrl(urlMap);
  }

  async function fetchRemote(kind: "logos" | "assets") {
    const url = fetchUrl.get(kind) || "";
    if (!url.trim() || busy || fetchBusy || !spec) return;
    setFetchBusy(true); setMessage(""); setError("");
    try {
      const updated = await api.fetchRemoteImage(projectId, kind, url.trim());
      setSpec(updated);
      setFetchUrl(prev => { const m = new Map(prev); m.delete(kind); return m; });
      setMessage(`Imported from ${url}. Review the results below.`);
    } catch(e) { setError(e instanceof Error ? e.message : "Could not download this image."); }
    finally { setFetchBusy(false); }
  }

  async function deleteAsset(kind: "logos" | "assets", name: string, ev: React.MouseEvent) {
    ev.stopPropagation();
    if (busy || !spec) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await api.deleteBrandAsset(projectId, kind, name);
      const list = spec[kind].filter(i => i.name !== name);
      setSpec({...spec, [kind]: list});
      setMessage(`Removed "${name}".`);
    } catch(e) { setError(e instanceof Error ? e.message : "Could not delete the asset."); }
    finally { setBusy(false); }
  }

// ... rest of file unchanged — find and replace the existing thumbnail line
  const field = "rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground";
  const action = "rounded-full border border-border px-4 py-2 text-sm hover:bg-raised disabled:opacity-50";
  return <div className="mx-auto max-w-[850px] py-4">
    <Link href="/brand" className="text-sm text-primary hover:underline">Back to brand systems</Link>
    <h1 className="mt-4 text-3xl font-bold">{name}</h1>
    <p className="mt-2 text-sm text-muted-foreground">Save named colors, font preferences, logos, and reference images. Font names do not install font files.</p>
    {error && <p role="alert" className="mt-4 text-sm text-destructive">{error}</p>}
    {message && <p role="status" className="mt-4 text-sm text-muted-foreground">{message}</p>}
    {!spec ? <p className="mt-6">{error ? "Brand settings are unavailable." : "Loading visual settings…"}</p> : <>
      <form className="mt-8 space-y-3" onSubmit={e => {e.preventDefault(); void importWebsite();}}>
        <label htmlFor="brand-website" className="block text-xl font-semibold">Import from a website</label>
        <p id="brand-website-help" className="text-sm text-muted-foreground">Add detected colors and font preferences from a public website. Existing settings are kept; new results save immediately. Upload logos separately below.</p>
        <div className="flex flex-wrap gap-2">
          <input id="brand-website" aria-describedby="brand-website-help" value={website} onChange={e=>setWebsite(e.target.value)} disabled={busy} maxLength={2048} placeholder="https://example.com" className={`${field} min-w-0 flex-1`} />
          <button type="submit" disabled={busy || dirty || !website.trim()} className={action}>Import brand settings</button>
        </div>
        {dirty && <p className="text-sm text-muted-foreground">Save your color and font edits before importing.</p>}
      </form>
      <fieldset disabled={busy} className="mt-8 space-y-3"><legend className="text-xl font-semibold">Colors</legend>
        <p className="text-sm text-muted-foreground">Use Background, Main text, and Accent to style generated presentations.</p>
        {spec.colors.map((color, i) => <div key={i} className="flex flex-wrap gap-2">
          <input aria-label={`Color ${i+1} name`} value={color.name} maxLength={40} className={`${field} flex-1`} onChange={e => { setSpec({...spec, colors:spec.colors.map((c,j)=>j===i?{...c,name:e.target.value}:c)}); setDirty(true); }} />
          <input aria-label={`Color ${i+1} value`} type="color" value={color.hex} className="h-10 w-16 rounded border border-input" onChange={e => { setSpec({...spec, colors:spec.colors.map((c,j)=>j===i?{...c,hex:e.target.value}:c)}); setDirty(true); }} />
          <button type="button" className={action} onClick={() => { setSpec({...spec,colors:spec.colors.filter((_,j)=>i!==j)}); setDirty(true); }}>Remove<span className="sr-only"> color {i+1}</span></button>
        </div>)}
        <button type="button" disabled={spec.colors.length>=12} className={action} onClick={() => {setSpec({...spec, colors:[...spec.colors,{name:["Background","Main text","Accent"][spec.colors.length] || "Color",hex:["#152330","#FFFFFF","#70DCE0"][spec.colors.length] || "#FFFFFF"}]});setDirty(true);}}>Add color</button>
      </fieldset>
      <fieldset disabled={busy} className="mt-8 space-y-3"><legend className="text-xl font-semibold">Fonts</legend>
        {spec.fonts.map((font,i)=><div key={i} className="flex flex-wrap gap-2">
          <input aria-label={`Font ${i+1} role`} value={font.role} maxLength={40} className={field} onChange={e=>{setSpec({...spec,fonts:spec.fonts.map((f,j)=>j===i?{...f,role:e.target.value}:f)});setDirty(true);}} />
          <input aria-label={`Font ${i+1} family`} value={font.family} maxLength={60} className={`${field} flex-1`} onChange={e=>{setSpec({...spec,fonts:spec.fonts.map((f,j)=>j===i?{...f,family:e.target.value}:f)});setDirty(true);}} />
          <button type="button" className={action} onClick={()=>{setSpec({...spec,fonts:spec.fonts.filter((_,j)=>j!==i)});setDirty(true);}}>Remove<span className="sr-only"> font {i+1}</span></button>
        </div>)}
        <button type="button" disabled={spec.fonts.length>=10} className={action} onClick={()=>{setSpec({...spec,fonts:[...spec.fonts,{role:"Body",family:"Arial"}]});setDirty(true);}}>Add font preference</button>
      </fieldset>
      <button type="button" disabled={busy || !dirty || spec.colors.some(c=>!c.name.trim()) || spec.fonts.some(f=>!f.role.trim() || !f.family.trim())} onClick={save} className="mt-6 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50">{busy ? "Working…" : "Save colors and fonts"}</button>
      {(["logos","assets"] as const).map(kind=><section key={kind} className="mt-10">
        <h2 className="text-xl font-semibold">{kind === "logos" ? "Logos" : "Reference images"}</h2>
        <p className="mt-1 text-sm text-muted-foreground">PNG, JPEG, or WebP, up to 10 MB and 20 megapixels. Uploads save immediately.</p>
        <div className="mt-4 flex flex-wrap gap-4">
          {spec[kind].map(image=><figure key={image.name} className="relative w-36 group">
            <button onClick={e=>deleteAsset(kind,image.name,e)} title="Remove" aria-label={`Remove ${image.name}`} className="absolute top-0 right-0 z-10 m-1 rounded-full bg-destructive p-1 text-white opacity-0 transition-opacity group-hover:opacity-100"><svg width="12" height="12" viewBox="0 0 12 12"><path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.5"/></svg></button>
            <img src={assetUrl(image.url) || undefined} alt={image.name} className="h-28 w-36 rounded-lg border border-border object-contain"/>
            <figcaption className="mt-1 truncate text-xs text-muted-foreground">{image.name}</figcaption></figure>)}</div>
        {/* "Download from URL" toggle / input row */}
        {fetchUrl.has(kind) ? (
          <div className="mt-3 flex gap-2">
            <input type="url" placeholder="https://example.com/logo.png" value={fetchUrl.get(kind)||""} onChange={e=>{const m=new Map(fetchUrl);m.set(kind,e.target.value);setFetchUrl(m);}} className="flex-1 rounded border border-input bg-background px-3 py-2 text-sm" />
            <button type="button" disabled={busy||fetchBusy||!fetchUrl.get(kind)||spec[kind].length>=20} onClick={()=>fetchRemote(kind)} className="rounded-full border border-border px-4 py-2 text-sm hover:bg-raised disabled:opacity-50">Download</button>
            <button type="button" onClick={()=>{const m=new Map(fetchUrl);m.delete(kind);setFetchUrl(m);}} className="rounded-full border border-border px-3 py-2 text-sm hover:bg-rais">Cancel</button></div>
        ) : (
          <button type="button" disabled={busy||spec[kind].length>=20} onClick={()=>{const m=new Map(fetchUrl);m.set(kind,"");setFetchUrl(m);}} className="mt-3 rounded-full border border-border px-4 py-2 text-sm hover:bg-raised">{kind==="logos"?"Add logo from URL":"Add reference image from URL"}</button>
        )}

        <input type="file" disabled={busy || spec[kind].length>=20} accept="image/png,image/jpeg,image/webp" aria-label={`Upload ${kind === "logos" ? "logo" : "reference image"}`} className="mt-4 max-w-full text-sm" onChange={e=>{void upload(kind,e.target.files?.[0]);e.target.value="";}} />
      </section>)}
    </>}
  </div>;
}
