import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import * as d3 from 'd3'
import { useNavigate } from 'react-router-dom'
import { Grid, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

type NodeKind = 'driver' | 'header' | 'api' | 'macro'
type RelationKind = 'include' | 'api' | 'macro'

interface DependencyNode extends d3.SimulationNodeDatum {
  id: string
  label: string
  kind: NodeKind
  path: string
  detail: string
}

interface DependencyLink extends d3.SimulationLinkDatum<DependencyNode> {
  source: string | DependencyNode
  target: string | DependencyNode
  relation: RelationKind
}

interface DriverGraph {
  key: string
  label: string
  nodes: DependencyNode[]
  links: DependencyLink[]
}

const DRIVER_GRAPHS: DriverGraph[] = [
  {
    key: 'wcd934x',
    label: 'wcd934x.c',
    nodes: [
      {
        id: 'wcd934x.c',
        label: 'wcd934x.c',
        kind: 'driver',
        path: 'sound/soc/codecs/wcd934x.c',
        detail: 'Primary downstream Qualcomm codec driver under migration.',
      },
      {
        id: 'soc.h',
        label: 'soc.h',
        kind: 'header',
        path: 'include/sound/soc.h',
        detail: 'Core SoC audio interfaces and helper contracts.',
      },
      {
        id: 'dapm.h',
        label: 'dapm.h',
        kind: 'header',
        path: 'include/sound/soc-dapm.h',
        detail: 'DAPM graph and widget definitions.',
      },
      {
        id: 'clk.h',
        label: 'clk.h',
        kind: 'header',
        path: 'include/linux/clk.h',
        detail: 'Clock framework interfaces used by codec startup paths.',
      },
      {
        id: 'snd_soc_dai_set_sysclk',
        label: 'snd_soc_dai_set_sysclk()',
        kind: 'api',
        path: 'sound/soc/soc-core.c',
        detail: 'DAI clock programming API used during stream bring-up.',
      },
      {
        id: 'snd_soc_component_update_bits',
        label: 'snd_soc_component_update_bits()',
        kind: 'api',
        path: 'sound/soc/soc-component.c',
        detail: 'Register update helper for component register map writes.',
      },
      {
        id: 'WCD934X_RX_PATH',
        label: 'WCD934X_RX_PATH',
        kind: 'macro',
        path: 'sound/soc/codecs/wcd934x.c',
        detail: 'Macro wiring receive path control flow in codec bring-up.',
      },
    ],
    links: [
      { source: 'wcd934x.c', target: 'soc.h', relation: 'include' },
      { source: 'wcd934x.c', target: 'dapm.h', relation: 'include' },
      { source: 'wcd934x.c', target: 'clk.h', relation: 'include' },
      { source: 'soc.h', target: 'snd_soc_dai_set_sysclk', relation: 'api' },
      { source: 'dapm.h', target: 'snd_soc_component_update_bits', relation: 'api' },
      { source: 'wcd934x.c', target: 'WCD934X_RX_PATH', relation: 'macro' },
      { source: 'WCD934X_RX_PATH', target: 'snd_soc_component_update_bits', relation: 'macro' },
    ],
  },
  {
    key: 'wsa883x',
    label: 'wsa883x.c',
    nodes: [
      {
        id: 'wsa883x.c',
        label: 'wsa883x.c',
        kind: 'driver',
        path: 'sound/soc/codecs/wsa883x.c',
        detail: 'Smart amplifier codec driver candidate for upstream prep.',
      },
      {
        id: 'regmap.h',
        label: 'regmap.h',
        kind: 'header',
        path: 'include/linux/regmap.h',
        detail: 'Register map abstractions for device I/O.',
      },
      {
        id: 'soundwire.h',
        label: 'soundwire.h',
        kind: 'header',
        path: 'include/linux/soundwire/sdw.h',
        detail: 'SoundWire bus transport contracts.',
      },
      {
        id: 'snd_soc_component_read',
        label: 'snd_soc_component_read()',
        kind: 'api',
        path: 'sound/soc/soc-component.c',
        detail: 'Component register read path used by state checks.',
      },
      {
        id: 'snd_soc_component_write',
        label: 'snd_soc_component_write()',
        kind: 'api',
        path: 'sound/soc/soc-component.c',
        detail: 'Component register write helper for sequence updates.',
      },
      {
        id: 'WSA883X_GAIN_MASK',
        label: 'WSA883X_GAIN_MASK',
        kind: 'macro',
        path: 'sound/soc/codecs/wsa883x.c',
        detail: 'Gain-field mask macro used during path programming.',
      },
    ],
    links: [
      { source: 'wsa883x.c', target: 'regmap.h', relation: 'include' },
      { source: 'wsa883x.c', target: 'soundwire.h', relation: 'include' },
      { source: 'regmap.h', target: 'snd_soc_component_read', relation: 'api' },
      { source: 'regmap.h', target: 'snd_soc_component_write', relation: 'api' },
      { source: 'wsa883x.c', target: 'WSA883X_GAIN_MASK', relation: 'macro' },
      { source: 'WSA883X_GAIN_MASK', target: 'snd_soc_component_write', relation: 'macro' },
    ],
  },
]

const RELATION_STYLE: Record<RelationKind, string> = {
  include: '0',
  api: '7 4',
  macro: '2 3',
}

const NODE_COLORS: Record<NodeKind, string> = {
  driver: '#1e3a8a',
  header: '#475569',
  api: '#0f766e',
  macro: '#92400e',
}

function endpointId(endpoint: string | DependencyNode): string {
  return typeof endpoint === 'string' ? endpoint : endpoint.id
}

export default function ArchitectureLab() {
  const navigate = useNavigate()
  const svgRef = useRef<SVGSVGElement | null>(null)

  const [graphKey, setGraphKey] = useState(DRIVER_GRAPHS[0].key)
  const [selectedNodeId, setSelectedNodeId] = useState('')

  const activeGraph = useMemo(() => {
    return DRIVER_GRAPHS.find((graph) => graph.key === graphKey) ?? DRIVER_GRAPHS[0]
  }, [graphKey])

  const selectedNode = useMemo(() => {
    return activeGraph.nodes.find((node) => node.id === selectedNodeId) ?? null
  }, [activeGraph, selectedNodeId])

  const selectedConnections = useMemo(() => {
    if (!selectedNodeId) {
      return []
    }

    const nodeById = new Map(activeGraph.nodes.map((node) => [node.id, node]))
    return activeGraph.links
      .filter((link) => endpointId(link.source) === selectedNodeId || endpointId(link.target) === selectedNodeId)
      .map((link) => {
        const sourceId = endpointId(link.source)
        const targetId = endpointId(link.target)
        return {
          relation: link.relation,
          source: nodeById.get(sourceId)?.label || sourceId,
          target: nodeById.get(targetId)?.label || targetId,
        }
      })
  }, [activeGraph, selectedNodeId])

  useEffect(() => {
    if (!svgRef.current) {
      return
    }

    const width = 980
    const height = 520
    const nodes: DependencyNode[] = activeGraph.nodes.map((node) => ({ ...node }))
    const links: DependencyLink[] = activeGraph.links.map((link) => ({ ...link }))

    const highlightedNodes = new Set<string>()
    const highlightedLinks = new Set<string>()
    if (selectedNodeId) {
      for (const link of links) {
        const sourceId = endpointId(link.source)
        const targetId = endpointId(link.target)
        if (sourceId === selectedNodeId || targetId === selectedNodeId) {
          highlightedNodes.add(sourceId)
          highlightedNodes.add(targetId)
          highlightedLinks.add(`${sourceId}->${targetId}`)
        }
      }
      highlightedNodes.add(selectedNodeId)
    }

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    svg
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('width', '100%')
      .attr('height', height)
      .style('background', '#f8fafc')
      .style('border', '1px solid #dbe3ec')
      .style('borderRadius', '10px')

    const root = svg.append('g')

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.5, 2.8])
      .on('zoom', (event) => {
        root.attr('transform', event.transform.toString())
      })
    svg.call(zoom as d3.ZoomBehavior<SVGSVGElement, unknown>)

    const link = root
      .append('g')
      .attr('stroke-linecap', 'round')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke-width', 2)
      .attr('stroke', (d) => {
        if (!selectedNodeId) {
          return '#94a3b8'
        }
        const key = `${endpointId(d.source)}->${endpointId(d.target)}`
        return highlightedLinks.has(key) ? '#0f172a' : '#cbd5e1'
      })
      .attr('stroke-dasharray', (d) => RELATION_STYLE[d.relation])

    const node = root
      .append('g')
      .selectAll<SVGGElement, DependencyNode>('g.node')
      .data(nodes)
      .join('g')
      .attr('class', 'node')
      .style('cursor', 'pointer')
      .on('click', (_event, d) => {
        setSelectedNodeId(d.id)
      })
      .on('dblclick', (_event, d) => {
        if (!d.path) {
          return
        }
        navigate(`/debug?source=${encodeURIComponent(d.path)}`)
      })

    node
      .append('circle')
      .attr('r', (d) => (d.kind === 'driver' ? 19 : 15))
      .attr('fill', (d) => NODE_COLORS[d.kind])
      .attr('stroke', (d) => {
        if (!selectedNodeId) {
          return '#ffffff'
        }
        return highlightedNodes.has(d.id) ? '#0f172a' : '#e2e8f0'
      })
      .attr('stroke-width', (d) => (d.id === selectedNodeId ? 3 : 1.5))

    node
      .append('text')
      .text((d) => d.label)
      .attr('font-size', 11)
      .attr('text-anchor', 'middle')
      .attr('dy', 31)
      .attr('fill', '#0f172a')
      .attr('font-weight', (d) => (d.kind === 'driver' ? 700 : 500))

    const simulation = d3
      .forceSimulation<DependencyNode>(nodes)
      .force(
        'link',
        d3
          .forceLink<DependencyNode, DependencyLink>(links)
          .id((d) => d.id)
          .distance(130),
      )
      .force('charge', d3.forceManyBody().strength(-560))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide<DependencyNode>().radius(36))

    const drag = d3
      .drag<SVGGElement, DependencyNode>()
      .on('start', (event, d) => {
        if (!event.active) {
          simulation.alphaTarget(0.2).restart()
        }
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) {
          simulation.alphaTarget(0)
        }
        d.fx = null
        d.fy = null
      })

    node.call(drag)

    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as DependencyNode).x || 0)
        .attr('y1', (d) => (d.source as DependencyNode).y || 0)
        .attr('x2', (d) => (d.target as DependencyNode).x || 0)
        .attr('y2', (d) => (d.target as DependencyNode).y || 0)

      node.attr('transform', (d) => `translate(${d.x || 0}, ${d.y || 0})`)
    })

    return () => {
      simulation.stop()
    }
  }, [activeGraph, navigate, selectedNodeId])

  return (
    <PageContainer>
      <PageHeader
        title="Architecture Lab"
        subtitle="Dependency graph visualization for driver includes, API usage, and macro relationships."
      />

      <SectionCard title="Dependency Graph Controls">
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            value={graphKey}
            onChange={(event) => {
              setGraphKey(event.target.value)
              setSelectedNodeId('')
            }}
            style={inputStyle}
          >
            {DRIVER_GRAPHS.map((graph) => (
              <option key={graph.key} value={graph.key}>
                {graph.label}
              </option>
            ))}
          </select>
          <button type="button" style={buttonStyle} onClick={() => setSelectedNodeId('')}>
            Clear Highlight
          </button>
          <MetaText>Click to highlight dependencies. Double-click to jump to Debugging Center.</MetaText>
        </div>
      </SectionCard>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Force-Directed Dependency Graph">
          <svg ref={svgRef} />
        </SectionCard>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <SectionCard title="Legend">
            <div style={legendGridStyle}>
              <div style={legendRowStyle}>
                <span style={{ ...legendSwatchStyle, background: NODE_COLORS.driver }} />
                <MetaText>Driver node</MetaText>
              </div>
              <div style={legendRowStyle}>
                <span style={{ ...legendSwatchStyle, background: NODE_COLORS.header }} />
                <MetaText>Header node</MetaText>
              </div>
              <div style={legendRowStyle}>
                <span style={{ ...legendSwatchStyle, background: NODE_COLORS.api }} />
                <MetaText>API node</MetaText>
              </div>
              <div style={legendRowStyle}>
                <span style={{ ...legendSwatchStyle, background: NODE_COLORS.macro }} />
                <MetaText>Macro node</MetaText>
              </div>
              <MetaText>Solid edge: #include</MetaText>
              <MetaText>Dashed edge: API usage</MetaText>
              <MetaText>Dotted edge: macro dependency</MetaText>
            </div>
          </SectionCard>

          <SectionCard title="Selected Node Details">
            {selectedNode ? (
              <div style={{ display: 'grid', gap: '0.45rem' }}>
                <MetaText>
                  <strong>{selectedNode.label}</strong>
                </MetaText>
                <MetaText>Type: {selectedNode.kind}</MetaText>
                <MetaText>Path: {selectedNode.path}</MetaText>
                <MetaText>{selectedNode.detail}</MetaText>
                <MetaText>Connected edges: {selectedConnections.length}</MetaText>
                <div style={{ display: 'grid', gap: '0.3rem', marginTop: '0.25rem' }}>
                  {selectedConnections.map((connection, index) => (
                    <MetaText key={`${connection.relation}-${index}`}>
                      {connection.source} -[{connection.relation}]-&gt; {connection.target}
                    </MetaText>
                  ))}
                </div>
              </div>
            ) : (
              <MetaText>Select a node to inspect dependency context.</MetaText>
            )}
          </SectionCard>
        </Grid>
      </div>
    </PageContainer>
  )
}

const inputStyle: CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.42rem 0.6rem',
  minWidth: '180px',
}

const buttonStyle: CSSProperties = {
  border: '1px solid #0f172a',
  borderRadius: '6px',
  background: '#0f172a',
  color: '#ffffff',
  padding: '0.4rem 0.65rem',
  fontSize: '0.82rem',
  cursor: 'pointer',
}

const legendGridStyle: CSSProperties = {
  display: 'grid',
  gap: '0.35rem',
}

const legendRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '0.45rem',
}

const legendSwatchStyle: CSSProperties = {
  width: '14px',
  height: '14px',
  borderRadius: '999px',
  display: 'inline-block',
}
