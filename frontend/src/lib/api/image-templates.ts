import { authedFetch, readError, request } from "./core";

export type TemplateField = {
  id: string;
  label: string;
  kind: "image" | "images" | "text" | "select";
  hint: string;
  placeholder: string;
  required: boolean;
  options?: string[];
  max_images?: number;
};

export type ImageTemplate = {
  id: string;
  name: string;
  description: string;
  categories: string[];
  engine: "edit" | "generate" | "enhance";
  fields: TemplateField[];
};

export type TemplateRun =
  | { kind: "generation"; template: string; generation: { id: string; status: string; prompt: string } }
  | { kind: "enhance"; template: string; job: { id: string; status: string } };

export type GenerationStatus = { id: string; status: string; file_url: string | null; error: string | null };

export const imageTemplatesApi = {
  catalog: () => request<{ categories: string[]; templates: ImageTemplate[] }>("/api/image-templates"),
  run: async (id: string, values: Record<string, string>, pictures: Record<string, File[]>) => {
    const form = new FormData();
    form.append("values", JSON.stringify(values));
    for (const [field, files] of Object.entries(pictures)) for (const f of files) form.append(field, f);
    const res = await authedFetch(`/api/image-templates/${id}/run`, { method: "POST", body: form });
    if (!res.ok) throw await readError(res);
    return (await res.json()) as TemplateRun;
  },
  generation: (id: string) => request<GenerationStatus>(`/api/generations/${id}`),
};
