# Mobile/APK Artifact Verification & Android WebView Networking (session bank, 2026-08-31)

Condensed from hermes-desktop-android Dispatch 6→6i (Capacitor Android wrapper for an Electron renderer). Class-level: verifying BUILT mobile artifacts and Android WebView network-layer debugging.

## Verify the BUILT artifact, never the source tree
A green `gradlew assembleDebug` + passing tests prove the SOURCES are good. The deliverable is the APK. Before shipping:
1. `aapt dump badging app.apk | head -1` → confirm `versionName` (must be the stamped version, see below).
2. `unzip -p app.apk assets/capacitor.config.json` → confirm the runtime config actually baked (androidScheme etc.). Generated `android/app/build/intermediates/**` can be STALE even when outputs/ APK is fresh — assert the packaged copy, not intermediates.
3. JS bundle: `unzip -p app.apk assets/public/bridge.js | grep -c <new-symbol>` — proves the injected/native-bridge changes shipped.
4. Native code may live in ANY classesN.dex (Capacitor puts app classes in classes4.dex, not classes.dex). `unzip -p app.apk classes4.dex | strings | grep -c <NewClassName>` and grep for new native string literals. Checking only classes.dex produced a false 'stale build' scare AND a wrong public claim — the false alarm was corrected in front of the user. Extract every dex before declaring code missing.
5. Run both test surfaces: JS suite (vitest) AND `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 ./gradlew :app:testDebugUnitTest`. Passing JVM tests do NOT prove the APK contains the classes.

## Version stamping (every APK, non-negotiable)
Two builds with the same versionName are indistinguishable on-device — burned a whole debug cycle (user ran old build; symptom matched the old bug; no way to tell). Pattern: repo-level `VERSION` file; installer script seds `versionName "..."` into the GENERATED build.gradle (the android/ tree is in .gitignore, so the stamp must be re-applied every sync). Bump VERSION, run installer, build, verify via aapt before delivery.

## Android WebView networking stack (each layer blocks separately)
| Layer | Guard | Fix |
|---|---|---|
| OS network | targetSdk 28+ cleartext | `android:usesCleartextTraffic="true"` in generated manifest |
| https page → http fetch | Chromium mixed content | Capacitor `android.allowMixedContent: true` |
| https page → ws:// | Separate WebSocket mixed-content rule — allowMixedContent does NOT lift it | Set `server.androidScheme: 'http'` (http://localhost is still a Chromium secure context: clipboard/crypto/SW unaffected; wss:// from http page is allowed) |
| Server side | CORS | Gateway must allow the WebView origin (`https?://(localhost|127.0.0.1)(:\d+)?$` regex) |
Debug sequence for 'Failed to fetch' in a Capacitor app against an http LAN gateway: check ALL four rows; symptoms are identical, layer differs. A fix at layer N does not fix layer N+1.

## Backgrounded-JavaScript class of bug (PKCE/login handoff)
When a WebView app hands off to a browser (Custom Tab) mid-flow: Android freezes renderer JS the moment the tab is foregrounded. Anything living in JS-promise state (pending waits, token exchange, tab auto-close) silently dies; activity recreation kills in-memory state entirely. Fix pattern: persist the handshake state to durable storage BEFORE opening the browser; persist the callback natively (Java) BEFORE serving the response page; complete the exchange on resume/boot from persisted state; keep the awake-JS path as a race-winner that clears persisted state (generation-scoped single-flight so live and resume paths cannot double-redeem single-use codes, and stale generations can never mutate newer logins' state). Symptom signature: server-side logs show the handoff completing (code issued) but the app showing nothing afterwards.

## Multi-round review convergence on lifecycle/race/auth code
Security-adjacent surfaces needed 3–4 fix rounds before SHIP (6b: 10 findings → 6c/6d: 1 race split into 2 → 6e: 5 findings → 6f: 1 cross-generation regression → 6g/6i clean). Fixes themselves introduced the next finding (single-flight fix created a cross-generation race). Expect it; budget 3–4 rounds; never force-ship on 'most findings fixed'. Codex re-reviews with `do NOT modify files` + writes findings to /tmp/<name>.md + stdout; ALWAYS capture to a FILE — `| tail -N` piping truncates the head of long reports and lost the Critical section once.

## Sibling concurrent-modification trap
Multiple Cursor/agent processes + orchestrator editing the same repo: patch tool warns 'modified by sibling subagent — read before writing'. The warning is real: re-read before patching, and only patch with anchors verified from a fresh read. Also seen: a patch anchored inside a heredoc corruption risk — after any patch to a script with heredocs, `bash -n` it before running.
