/** Landing page: what inteGREAT is, why it exists, and how it works — then a clear
    route into the workspace. Shown before the import screen so first-time visitors
    (e.g. judges on a live deployment) understand the product before touching it. */
import { Layout, LayoutContent, LayoutHeader } from "@astryxdesign/core/Layout";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { Grid } from "@astryxdesign/core/Grid";
import { Eyebrow } from "../flow/common";

const STEPS = [
  { n: "1", title: "Map it", body: "Point inteGREAT at your ESP32 project. It reads the code and your wiring notes, then draws a map of what depends on what — modules, pins, parts, power." },
  { n: "2", title: "Test it", body: "Run a test against simulated, recorded, or live hardware. Commands, board replies, and camera measurements land on one timeline — each labelled by where it came from." },
  { n: "3", title: "Fix it", body: "Get a ranked list of likely causes and one suggested next check at a time. Make a repair, re-run the same test, and verify the fix actually worked." },
];

const FEATURES = [
  { title: "A map of your system", body: "Every function, pin, wire, and part as a graph you can filter to hardware, software, or both — so a wiring note is never confused with a line of code." },
  { title: "Evidence, not guesses", body: "Every claim shows what backs it: observed, verified, inferred, or unknown. A missing camera measurement is \"measurement unavailable\" — never a fake failure." },
  { title: "Guided next steps", body: "One emphasized action at a time — check this wire, inspect this line of code, record a bench result. Safe read-only tools; nothing flashes or changes your board." },
  { title: "Timeline of what happened", body: "What you asked, what the board said, what the camera saw, and the verdict — scrubbed step by step, correlated across sources." },
  { title: "Optional AI review", body: "Specialist agents can review the evidence and a Devin session can draft a software fix in a sandbox — clearly marked as AI work, gated by your approvals." },
  { title: "Works without extras", body: "No AI keys, no camera, no board? The whole debug loop still runs — the built-in checks and two simulated demos carry the full story." },
];

export function LandingScreen({ onEnter }: { onEnter: () => void }) {
  return (
    <Layout contentWidth={1040} header={
      <LayoutHeader>
        <HStack hAlign="between" vAlign="center" width="100%">
          <span className="brand" aria-hidden><span className="bmark">inte</span>GREAT</span>
          <Button label="Open the workspace" variant="primary" onClick={onEnter} />
        </HStack>
      </LayoutHeader>
    } content={
      <LayoutContent>
        <VStack gap={8} paddingBlock={10}>
          <VStack gap={3} maxWidth={760}>
            <Eyebrow>Graph-first debugging for physical projects</Eyebrow>
            <Heading level={1} type="display-1">Your code said move the servo. The arm didn't move. Now what?</Heading>
            <Text type="large" color="secondary">
              inteGREAT shows you why — it maps your ESP32 code to the physical wiring, runs a test,
              records what actually happened, and walks you to the fix, one check at a time.
            </Text>
            <HStack gap={2} paddingBlockStart={2}>
              <Button label="Open the workspace" variant="primary" onClick={onEnter} />
            </HStack>
          </VStack>

          <Card padding={5} variant="muted">
            <VStack gap={2} maxWidth={760}>
              <Heading level={3}>Why this exists</Heading>
              <Text type="body" color="secondary">
                Hardware bugs hide in the gap between code and physics. The serial log says the board
                acknowledged the command — and the arm still doesn't move. Is it the pin the code drives,
                the wire it's soldered to, or the power feeding it? Logs alone can't tell you.
              </Text>
              <Text type="body" color="secondary">
                inteGREAT keeps those questions separate. Every finding is labelled by what actually
                backs it — a simulated test is never passed off as real hardware, and a measurement the
                camera couldn't take is called exactly that.
              </Text>
            </VStack>
          </Card>

          <VStack gap={3}>
            <Heading level={2}>How it works</Heading>
            <Grid columns={{ minWidth: 280, repeat: "fill" }} gap={3}>
              {STEPS.map((s) => (
                <Card key={s.n} padding={4}>
                  <VStack gap={2}>
                    <HStack gap={2} vAlign="center">
                      <Text type="large" color="secondary">{s.n}</Text>
                      <Text type="large" weight="semibold">{s.title}</Text>
                    </HStack>
                    <Text type="body" color="secondary">{s.body}</Text>
                  </VStack>
                </Card>
              ))}
            </Grid>
          </VStack>

          <VStack gap={3}>
            <VStack gap={1}>
              <Heading level={2}>What's inside</Heading>
              <Text type="body" color="secondary">Everything below works today — including two simulated demos you can click through in about five minutes.</Text>
            </VStack>
            <Grid columns={{ minWidth: 300, repeat: "fill" }} gap={3}>
              {FEATURES.map((f) => (
                <Card key={f.title} padding={4}>
                  <VStack gap={1}>
                    <Text type="body" weight="semibold">{f.title}</Text>
                    <Text type="supporting" color="secondary">{f.body}</Text>
                  </VStack>
                </Card>
              ))}
            </Grid>
          </VStack>

          <Card padding={5}>
            <HStack hAlign="between" vAlign="center" gap={4} wrap="wrap">
              <VStack gap={1} maxWidth={560}>
                <Heading level={3}>Try it on a simulated rig</Heading>
                <Text type="body" color="secondary">
                  Two failure stories are built in — a wrong pin in the code, and a disconnected signal
                  wire. Nothing touches real hardware; every observation is labelled as simulated.
                </Text>
              </VStack>
              <Button label="Open the workspace" variant="primary" onClick={onEnter} />
            </HStack>
          </Card>
        </VStack>
      </LayoutContent>
    } />
  );
}
