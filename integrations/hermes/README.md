# `/vision` — Skylinee Vision AI skill

Connects the native Hermes execution engine used by the deployed Skylinee bridge
to [Skylinee Vision AI](https://github.com/cojarman3011/skylinee-vision-ai).
It calls the existing `POST /api/detect` endpoint; it does not copy model code or
replace YOLOv8n/COCO with a language-model guess.

## Usage

```text
/vision /workspace/photo.jpg
```

An attached image also works **when native Hermes attachment processing provides
an accessible image path**. Upload forwarding alone does not prove that a selected
provider exposes that path to tools. `/vision` without an accessible image asks for
one. Results include labels, confidence scores, boxes, an annotated image link,
and individual crop links. Video inference is not implemented.

## Install in the actual runtime

The skill files must be visible inside the Hermes execution environment, not merely
on the Pi running Open WebUI. The service URL must also be reachable from that
environment. Do not assume `localhost` crosses container boundaries.

1. Run the existing vision service using its own repository's installation guide.
2. Set `SKYLINEE_VISION_URL` in the environment inherited by Hermes, pointing to that
   service origin. An example is `http://127.0.0.1:8015` only when it shares the
   same network namespace. This client neither exposes the service publicly nor
   changes the existing native execution/approval settings.
3. Install the skill into the **actual** Hermes skills directory:

   ```bash
   python3 integrations/hermes/install_vision.py --skills-dir /ACTUAL/HERMES/SKILLS
   ```

4. For Open WebUI's OpenAI chat API, install the bridge dispatcher as well. CLI
   slash-command support does not establish that OpenAI API messages are expanded.
   The optional patch recognizes `/vision` in the newest user message and adds a
   trusted instruction to load the installed skill through native `skill_view`.
   It preserves image content, history, provider routing, and native tool approval.

   ```bash
   python3 integrations/hermes/install_vision.py \
     --skills-dir /ACTUAL/HERMES/SKILLS \
     --bridge-file /ACTUAL/skylinee_harness/hermes_bridge.py
   ```

   Choose step 3 **or** the combined step 4, not both: existing skills are never
   overwritten. The dispatcher patch checks the known 0.3.4 source insertion point
   and saves a backup. It does not modify the separate 0.6.0 agent implementation.
   Run in a staged copy first. For containers, stage/rebuild the harness image with
   the patched module and persist the skill in the native Hermes runtime; editing
   host files does not change an already-built image. No restart is performed by
   the installer. Any already-running bridge needs its changed module reloaded.

## Verification and current status

```bash
python3 -m unittest discover -s integrations/hermes/tests -v
```

Ten tests verify command boundaries, preserved multimodal input, unchanged routing,
multipart upload construction, output links, zero detections, invalid responses,
input rejection, and redirect refusal. Transport tests use a mocked detector;
they do not establish actual model accuracy or live inference.

**Prepared and tested integration; not installed or verified on Corey's LAN.**
After installation, verify `vision` appears in the authenticated `/v1/skills` list,
submit an image with `/vision`, and inspect the native run's `skill_view` and
`terminal` events plus the actual detection JSON before declaring it live.
No production services were changed for this integration.

The helper uses Python's standard library. The independent vision service retains
its own AGPL license, dependencies, model attribution, limits, and retention policy.
