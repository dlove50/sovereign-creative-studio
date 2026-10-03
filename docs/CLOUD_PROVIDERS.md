# HeyGen and ElevenLabs in Sovereign

Open **Apps → Cloud studio** (`/cloud-studio`). These tools are owner/admin-only and do not change the local generation defaults.

## Connect your accounts

1. Open **Provider settings** (`/admin/integrations`).
2. Enter your own HeyGen and/or ElevenLabs API key in the corresponding card, save it, and enable that provider.
3. Use **Test connection**. This reads a catalog only; it does not generate paid media. Generation permissions, quota and plan eligibility are checked by the provider when a request runs.
4. Return to Cloud Studio. Browse profiles or enter a profile ID, supply text or a recording, and submit the chosen operation.

Website/Gmail login sessions are not API credentials. Do not put API keys in source files, browser storage or chat. Keys use Sovereign's existing backend secrets store and are masked in settings. The public storage route now blocks the secrets folder.

## Supported operations

| Tool | Provider | Local result |
| --- | --- | --- |
| Avatar video | HeyGen v3 | MP4, using an original public/private avatar look and its default or selected HeyGen voice |
| Text to speech | ElevenLabs | MP3 |
| Sound effects | ElevenLabs | MP3; 0.5–30 seconds, optional seamless loop |
| Voice changer | ElevenLabs | Converted audio |
| Speech to text | ElevenLabs | UTF-8 text and JSON with provider word/speaker information |
| Dubbing | ElevenLabs automatic dubbing (documented legacy API) | MP3 or MP4 in the selected language; watermark requested |
| Audio isolation | ElevenLabs | Cleaned audio |
| Music | ElevenLabs music_v1 | MP3; 3–600 seconds, optional instrumental-only |
| Transcript timing | ElevenLabs forced alignment | Word/character timing JSON plus the supplied transcript |

Voice/avatar catalogs are paginated and fetched on demand. HeyGen exposes public/private ownership through these endpoints; the website's category tabs and Favorites are not assumed to be API filters. Account voices are not promised to be free. The integration does not scrape a sound library, clone provider-owned profiles, download model weights, or grant offline use of their voices.

## Where files go

The active absolute output directory is shown in Cloud Studio. By default it is:

`backend/storage/cloud/<request UUID>/`

Each job has a `job.json` record plus its completed files (`output.mp3`, `output.wav`, `output.mp4`, `transcript.txt`, `transcript.json`, as applicable). Preview or download them from Cloud Studio. Downloads copy the selected result to the browser's normal download destination. These results are not automatically inserted into every existing movie/editor picker; download and upload a result into those tools as needed.

Uploaded source files are limited to 100 MB and removed after submission finishes. Output downloads are limited to 1 GB. Raw job/source files are blocked from the public `/storage` mount; output downloads use the authenticated owner route. Backups continue to exclude API secrets.

## Jobs and billing

- Each submission explicitly names the provider and requires acknowledgement that it uses that account's allowance/credits. Sovereign's local credits do not pay the external provider.
- Submissions have a local UUID and are not automatically retried. Repeating the same request ID returns its existing job; different input with that ID is rejected.
- Up to three submissions can be active at once. HeyGen/dubbing remote IDs survive restarts.
- Cloud Studio checks remote progress every minute while open and saves completed media. You can also click **Check progress & save result** after returning later. There is no unattended remote poller when the page is closed.
- A restart during submission records an interruption rather than replaying a potentially billable request. Check the provider dashboard before submitting another copy.
- A failed result download can be retried by refreshing the existing remote job, without generating again. HeyGen downloads only allow its HTTPS media hosts; an unexpected CDN host requires dashboard download.

## API references

- [HeyGen avatar looks](https://developers.heygen.com/reference/list-avatar-looks), [voices](https://developers.heygen.com/reference/list-voices), [create video](https://developers.heygen.com/reference/create-video), [get video](https://developers.heygen.com/reference/get-video).
- [ElevenLabs voices](https://elevenlabs.io/docs/api-reference/voices/search), [speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), [sound effects](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert), [voice changer](https://elevenlabs.io/docs/api-reference/speech-to-speech/convert), [transcription](https://elevenlabs.io/docs/api-reference/speech-to-text/convert), [dubbing](https://elevenlabs.io/docs/api-reference/legacy/dubbing/create), [dub download](https://elevenlabs.io/docs/api-reference/legacy/dubbing/audio/get), [isolation](https://elevenlabs.io/docs/api-reference/audio-isolation/convert).

Contract tests use mocked HTTP responses, never real provider keys or paid calls. An authenticated generation smoke test remains necessary once the owner configures keys and chooses a sample to generate.
