import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import * as d3 from 'd3'
import { apiRequest, toErrorMessage } from '../api/client'
import { API_ROUTES } from '../config'
import { useApiData } from '../hooks/useApiData'
import { Grid, JsonBlock, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

interface RuleRecord {
  id: string
  subsystem_id: string
  category: string
  downstream_pattern: string
  upstream_equivalent: string
  description: string
  confidence: number
  source_refs?: string | null
}

interface RulesResponse {
  rules: RuleRecord[]
}

interface SearchResponse {
  results: RuleRecord[]
  count: number
}

type GraphLayout = 'force' | 'radial'
type GraphNodeType = 'rule' | 'category' | 'evidence' | 'subsystem' | 'section'

interface EvidenceFile {
  path: string
  name: string
  extension: string
  size_bytes: number
  modified_at: string
}

interface EvidenceSection {
  root: string
  files: EvidenceFile[]
}

interface EvidenceIndexResponse {
  generated_at: string
  sections: Record<string, EvidenceSection>
}

interface GraphNode extends d3.SimulationNodeDatum {
  id: string
  label: string
  nodeType: GraphNodeType
  meta: Record<string, unknown>
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  source: string | GraphNode
  target: string | GraphNode
  relation: string
  detail: string
}

interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

const NODE_COLORS: Record<GraphNodeType, string> = {
  rule: '#1d4ed8',
  category: '#475569',
  evidence: '#0f766e',
  subsystem: '#92400e',
  section: '#6d28d9',
}

function endpointId(value: string | GraphNode): string {
  return typeof value === 'string' ? value : value.id
}

function parseSourceRefs(raw: string | null | undefined): string[] {
  if (!raw) {
    return []
  }
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      return parsed.map((entry) => String(entry))
    }
  } catch {
    // Non-JSON source refs fallback handled below.
  }
  return raw
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
}

function buildGraph(rules: RuleRecord[], evidenceSections: Record<string, EvidenceSection>): GraphData {
  const nodes = new Map<string, GraphNode>()
  const links: GraphLink[] = []

  function ensureNode(node: GraphNode) {
    if (!nodes.has(node.id)) {
      nodes.set(node.id, node)
    }
  }

  for (const rule of rules) {
    const ruleId = `rule:${rule.id}`
    const categoryId = `category:${rule.category || 'uncategorized'}`
    const subsystemId = `subsystem:${rule.subsystem_id || 'unknown'}`

    ensureNode({
      id: ruleId,
      label: rule.downstream_pattern || rule.id,
      nodeType: 'rule',
      meta: {
        id: rule.id,
        description: rule.description,
        confidence: rule.confidence,
        upstream_equivalent: rule.upstream_equivalent,
      },
    })
    ensureNode({
      id: categoryId,
      label: rule.category || 'uncategorized',
      nodeType: 'category',
      meta: {},
    })
    ensureNode({
      id: subsystemId,
      label: `subsystem:${rule.subsystem_id || 'unknown'}`,
      nodeType: 'subsystem',
      meta: {},
    })

    links.push({
      source: categoryId,
      target: ruleId,
      relation: 'applies_to',
      detail: `Category ${rule.category || 'uncategorized'} applies to rule ${rule.id}`,
    })
    links.push({
      source: subsystemId,
      target: ruleId,
      relation: 'scoped_to',
      detail: `Rule scoped to subsystem ${rule.subsystem_id || 'unknown'}`,
    })

    const evidenceRefs = parseSourceRefs(rule.source_refs)
    const evidenceValues = evidenceRefs.length > 0 ? evidenceRefs : [rule.upstream_equivalent || rule.description || 'No evidence']
    evidenceValues.slice(0, 3).forEach((evidence, index) => {
      const evidenceId = `evidence:${rule.id}:${index}`
      ensureNode({
        id: evidenceId,
        label: evidence.length > 34 ? `${evidence.slice(0, 34)}...` : evidence,
        nodeType: 'evidence',
        meta: { raw: evidence },
      })
      links.push({
        source: ruleId,
        target: evidenceId,
        relation: 'supports',
        detail: evidence,
      })
    })
  }

  for (const [sectionName, sectionData] of Object.entries(evidenceSections)) {
    const sectionId = `section:${sectionName}`
    ensureNode({
      id: sectionId,
      label: sectionName,
      nodeType: 'section',
      meta: {
        root: sectionData.root,
        file_count: sectionData.files.length,
      },
    })

    sectionData.files.slice(0, 40).forEach((file, index) => {
      const fileId = `evidence:${sectionName}:${index}:${file.path}`
      ensureNode({
        id: fileId,
        label: file.name,
        nodeType: 'evidence',
        meta: {
          path: file.path,
          extension: file.extension,
          size_bytes: file.size_bytes,
          modified_at: file.modified_at,
        },
      })
      links.push({
        source: sectionId,
        target: fileId,
        relation: 'depends_on',
        detail: file.path,
      })
    })
  }

  return {
    nodes: Array.from(nodes.values()),
    links,
  }
}

export default function KnowledgeGraphCenter() {
  const svgRef = useRef<SVGSVGElement | null>(null)

  const [query, setQuery] = useState('audio')
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null)
  const [searchError, setSearchError] = useState('')
  const [searching, setSearching] = useState(false)
  const [layoutMode, setLayoutMode] = useState<GraphLayout>('force')

  const [exportResult, setExportResult] = useState<unknown>(null)
  const [exportError, setExportError] = useState('')
  const [exporting, setExporting] = useState(false)
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [selectedLinkId, setSelectedLinkId] = useState('')

  const { data: rulesData } = useApiData<RulesResponse>(API_ROUTES.knowledge.rules(60), { intervalMs: 30_000 })
  const { data: evidenceData } = useApiData<EvidenceIndexResponse>(API_ROUTES.knowledge.evidenceIndex(120, 4), {
    intervalMs: 45_000,
  })

  const activeRules = useMemo(() => {
    if (searchResult?.results?.length) {
      return searchResult.results
    }
    return rulesData?.rules || []
  }, [rulesData?.rules, searchResult?.results])

  const evidenceSections = evidenceData?.sections || {}
  const evidenceFileCount = useMemo(() => {
    return Object.values(evidenceSections).reduce((acc, section) => acc + (section.files?.length || 0), 0)
  }, [evidenceSections])

  const graphData = useMemo(() => buildGraph(activeRules, evidenceSections), [activeRules, evidenceSections])

  const selectedNode = useMemo(() => graphData.nodes.find((node) => node.id === selectedNodeId) || null, [graphData.nodes, selectedNodeId])
  const selectedLink = useMemo(() => {
    if (!selectedLinkId) {
      return null
    }
    return graphData.links.find((link) => {
      const key = `${endpointId(link.source)}->${endpointId(link.target)}:${link.relation}`
      return key === selectedLinkId
    }) || null
  }, [graphData.links, selectedLinkId])

  useEffect(() => {
    if (!svgRef.current) {
      return
    }

    const width = 980
    const height = 560
    const nodes = graphData.nodes.map((node) => ({ ...node }))
    const links = graphData.links.map((link) => ({ ...link }))

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
      .scaleExtent([0.5, 2.6])
      .on('zoom', (event) => {
        root.attr('transform', event.transform.toString())
      })
    svg.call(zoom as d3.ZoomBehavior<SVGSVGElement, unknown>)

    const linkSelection = root
      .append('g')
      .selectAll<SVGLineElement, GraphLink>('line.edge')
      .data(links)
      .join('line')
      .attr('class', 'edge')
      .attr('stroke-width', 1.8)
      .attr('stroke', (link) => {
        const key = `${endpointId(link.source)}->${endpointId(link.target)}:${link.relation}`
        if (!selectedLinkId) {
          return '#94a3b8'
        }
        return key === selectedLinkId ? '#0f172a' : '#cbd5e1'
      })
      .attr('stroke-dasharray', (link) => (link.relation === 'supports' ? '6 4' : '0'))
      .style('cursor', 'pointer')
      .on('click', (_event, link) => {
        const key = `${endpointId(link.source)}->${endpointId(link.target)}:${link.relation}`
        setSelectedLinkId(key)
      })

    const nodeSelection = root
      .append('g')
      .selectAll<SVGGElement, GraphNode>('g.node')
      .data(nodes)
      .join('g')
      .attr('class', 'node')
      .style('cursor', 'pointer')
      .on('click', (_event, node) => {
        setSelectedNodeId(node.id)
        setSelectedLinkId('')
      })
      .on('contextmenu', (event, node) => {
        event.preventDefault()
        setSelectedNodeId(node.id)
      })

    nodeSelection
      .append('circle')
      .attr('r', (node) => (node.nodeType === 'rule' ? 16 : 13))
      .attr('fill', (node) => NODE_COLORS[node.nodeType])
      .attr('stroke', (node) => (node.id === selectedNodeId ? '#0f172a' : '#ffffff'))
      .attr('stroke-width', (node) => (node.id === selectedNodeId ? 3 : 1.4))

    nodeSelection
      .append('text')
      .text((node) => node.label)
      .attr('font-size', 10.5)
      .attr('text-anchor', 'middle')
      .attr('dy', 28)
      .attr('fill', '#0f172a')

    const simulation = d3
      .forceSimulation<GraphNode>(nodes)
      .force(
        'link',
        d3
          .forceLink<GraphNode, GraphLink>(links)
          .id((node) => node.id)
          .distance((link) => (link.relation === 'supports' ? 130 : 100)),
      )
      .force('charge', d3.forceManyBody().strength(-360))
      .force('collision', d3.forceCollide<GraphNode>().radius(24))
      .force('center', d3.forceCenter(width / 2, height / 2))

    if (layoutMode === 'radial') {
      const groups: Record<GraphNodeType, GraphNode[]> = {
        subsystem: [],
        category: [],
        rule: [],
        evidence: [],
        section: [],
      }
      nodes.forEach((node) => groups[node.nodeType].push(node))

      const centerX = width / 2
      const centerY = height / 2
      const rings: Record<GraphNodeType, number> = {
        subsystem: 80,
        category: 170,
        rule: 260,
        evidence: 340,
        section: 420,
      }

      ;(Object.keys(groups) as GraphNodeType[]).forEach((type) => {
        const group = groups[type]
        group.forEach((node, index) => {
          const angle = (Math.PI * 2 * index) / Math.max(1, group.length)
          node.x = centerX + rings[type] * Math.cos(angle)
          node.y = centerY + rings[type] * Math.sin(angle)
          node.fx = node.x
          node.fy = node.y
        })
      })
      simulation.alpha(0.2).restart()
    } else {
      nodes.forEach((node) => {
        node.fx = null
        node.fy = null
      })
    }

    const drag = d3
      .drag<SVGGElement, GraphNode>()
      .on('start', (event, node) => {
        if (!event.active) {
          simulation.alphaTarget(0.2).restart()
        }
        node.fx = node.x
        node.fy = node.y
      })
      .on('drag', (event, node) => {
        node.fx = event.x
        node.fy = event.y
      })
      .on('end', (event, node) => {
        if (!event.active) {
          simulation.alphaTarget(0)
        }
        if (layoutMode === 'radial') {
          return
        }
        node.fx = null
        node.fy = null
      })
    nodeSelection.call(drag)

    simulation.on('tick', () => {
      linkSelection
        .attr('x1', (link) => (link.source as GraphNode).x || 0)
        .attr('y1', (link) => (link.source as GraphNode).y || 0)
        .attr('x2', (link) => (link.target as GraphNode).x || 0)
        .attr('y2', (link) => (link.target as GraphNode).y || 0)
      nodeSelection.attr('transform', (node) => `translate(${node.x || 0}, ${node.y || 0})`)
    })

    return () => {
      simulation.stop()
    }
  }, [graphData, layoutMode, selectedLinkId, selectedNodeId])

  async function runSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
      setSearching(true)
      setSearchError('')
      try {
      const endpoint = API_ROUTES.knowledge.search(query, 60)
      const result = await apiRequest<SearchResponse>(endpoint)
      setSearchResult(result)
    } catch (error) {
      setSearchError(toErrorMessage(error))
      setSearchResult(null)
    } finally {
      setSearching(false)
    }
  }

  async function exportRules() {
    setExporting(true)
    setExportError('')
    try {
      const result = await apiRequest(API_ROUTES.knowledge.export(), {
        method: 'POST',
        body: JSON.stringify({ format: 'json' }),
      })
      setExportResult(result)
    } catch (error) {
      setExportError(toErrorMessage(error))
      setExportResult(null)
    } finally {
      setExporting(false)
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Knowledge Graph Center"
        subtitle="Rule/evidence relationship graph with click inspection and force/radial layout controls."
      />

      <Grid>
        <SectionCard title="Search Knowledge">
          <form onSubmit={runSearch} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={inputStyle}
              placeholder="Search term"
            />
            <button style={buttonStyle} type="submit" disabled={searching || !query.trim()}>
              {searching ? 'Searching...' : 'Search'}
            </button>
            <button
              style={buttonStyle}
              type="button"
              onClick={() => {
                setSearchResult(null)
                setSearchError('')
              }}
            >
              Clear Search
            </button>
          </form>
          <div style={{ marginTop: '0.75rem' }}>
            {searchError ? <MetaText>{searchError}</MetaText> : null}
            {searchResult ? (
              <MetaText>
                Search results: {searchResult.count} rule(s), graph nodes={graphData.nodes.length}, edges={graphData.links.length}
              </MetaText>
            ) : (
              <MetaText>
                Using live rules dataset and evidence index. rules={activeRules.length} | evidence_files={evidenceFileCount}
              </MetaText>
            )}
          </div>
        </SectionCard>

        <SectionCard title="Export Knowledge">
          <button style={buttonStyle} type="button" onClick={() => void exportRules()} disabled={exporting}>
            {exporting ? 'Exporting...' : 'Export JSON'}
          </button>
          <div style={{ marginTop: '0.75rem' }}>
            {exportError ? <MetaText>{exportError}</MetaText> : null}
            {exportResult ? <JsonBlock data={exportResult} /> : <MetaText>Export result appears here.</MetaText>}
          </div>
        </SectionCard>
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Knowledge Graph Visualization">
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.65rem' }}>
            <label style={{ fontSize: '0.84rem', color: '#475569' }}>
              Layout:
              <select value={layoutMode} onChange={(event) => setLayoutMode(event.target.value as GraphLayout)} style={inputStyle}>
                <option value="force">force</option>
                <option value="radial">radial</option>
              </select>
            </label>
            <MetaText>
              Nodes={graphData.nodes.length} | Links={graphData.links.length}
            </MetaText>
          </div>
          {graphData.nodes.length === 0 ? (
            <MetaText>
              No graph entities available from live rules/evidence sources. This page does not synthesize placeholder graph data.
            </MetaText>
          ) : null}
          <svg ref={svgRef} />
        </SectionCard>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <SectionCard title="Selected Node">
            {selectedNode ? <JsonBlock data={selectedNode} /> : <MetaText>Click or right-click a node to inspect details.</MetaText>}
          </SectionCard>
          <SectionCard title="Selected Relationship">
            {selectedLink ? (
              <JsonBlock
                data={{
                  source: endpointId(selectedLink.source),
                  target: endpointId(selectedLink.target),
                  relation: selectedLink.relation,
                  detail: selectedLink.detail,
                }}
              />
            ) : (
              <MetaText>Click an edge to inspect relation evidence.</MetaText>
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
  padding: '0.45rem 0.6rem',
  fontSize: '0.9rem',
  minWidth: '180px',
}

const buttonStyle: CSSProperties = {
  border: '1px solid #334155',
  borderRadius: '6px',
  background: '#334155',
  color: '#fff',
  padding: '0.48rem 0.75rem',
  cursor: 'pointer',
}
