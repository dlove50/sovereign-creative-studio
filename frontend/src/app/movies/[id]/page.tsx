import { MovieEditorView } from "@/components/movies/movie-editor-view";

export default function MoviePage({ params }: { params: { id: string } }) {
  return <MovieEditorView key={params.id} movieId={params.id} />;
}
