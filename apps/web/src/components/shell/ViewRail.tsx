/** Left icon rail — Roblox-Studio-style view switcher: icon + clear text label, grouped
 * sections, explicit selected state. Owns canvas mode (Map/Timeline) and graph layer
 * (All/Hardware/Software). Keyboard shortcuts D/E and H/S/C drive the same state. */
import { SideNav, SideNavSection, SideNavItem } from "@astryxdesign/core/SideNav";
import { Network, ListOrdered, Layers, Cpu, FileCode2 } from "lucide-react";
import type { GraphLayer } from "../../lib/api";
import type { CanvasMode } from "../graph/GraphView";

export function ViewRail({ mode, layer, onMode, onLayer }: {
  mode: CanvasMode;
  layer: GraphLayer;
  onMode: (m: CanvasMode) => void;
  onLayer: (l: GraphLayer) => void;
}) {
  return (
    <SideNav collapsible={{ defaultIsCollapsed: typeof window !== "undefined" && window.innerWidth < 1000 }}
             resizable={{ defaultWidth: 148, minWidth: 132, maxWidth: 240, autoSaveId: "integreat.rail" }}>
      <SideNavSection title="View">
        <SideNavItem label="Map" icon={<Network size={18} />} isSelected={mode === "deps"}
                     onClick={() => onMode("deps")} />
        <SideNavItem label="Timeline" icon={<ListOrdered size={18} />} isSelected={mode === "flow"}
                     onClick={() => onMode("flow")} />
      </SideNavSection>
      <SideNavSection title="Layer">
        <SideNavItem label="All" icon={<Layers size={18} />} isSelected={layer === "combined"}
                     onClick={() => onLayer("combined")} />
        <SideNavItem label="Hardware" icon={<Cpu size={18} />} isSelected={layer === "hardware"}
                     onClick={() => onLayer("hardware")} />
        <SideNavItem label="Software" icon={<FileCode2 size={18} />} isSelected={layer === "software"}
                     onClick={() => onLayer("software")} />
      </SideNavSection>
    </SideNav>
  );
}
