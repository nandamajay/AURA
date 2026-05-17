import { DataPanel } from './DataPanel'
import { Grid, PageContainer, PageHeader } from './PagePrimitives'

interface EndpointPanel {
  title: string
  endpoint: string
  intervalMs?: number
  includeAuth?: boolean
}

export default function EndpointGridPage({
  title,
  subtitle,
  panels,
}: {
  title: string
  subtitle: string
  panels: EndpointPanel[]
}) {
  return (
    <PageContainer>
      <PageHeader title={title} subtitle={subtitle} />
      <Grid>
        {panels.map((panel) => (
          <DataPanel
            key={`${panel.title}-${panel.endpoint}`}
            title={panel.title}
            endpoint={panel.endpoint}
            intervalMs={panel.intervalMs}
            includeAuth={panel.includeAuth}
          />
        ))}
      </Grid>
    </PageContainer>
  )
}
