export type TeachingAction = 'click' | 'observe' | 'input'
export type TeachingTrigger = 'first_visit' | 'manual' | 'event'

export interface TeachingStep {
  id: string
  title: string
  content: string
  targetElement?: string
  actionRequired?: TeachingAction
}

export interface TeachingFlow {
  id: string
  name: string
  trigger: TeachingTrigger
  steps: TeachingStep[]
}

export const DEFAULT_FLOWS: TeachingFlow[] = [
  {
    id: 'first_time_setup',
    name: 'Welcome to AURA',
    trigger: 'first_visit',
    steps: [
      {
        id: 'welcome',
        title: 'Welcome to AURA',
        content: "AURA helps upstream Qualcomm Audio drivers to the Linux kernel. Let's take a quick tour.",
        targetElement: '[data-testid=dashboard-title]',
        actionRequired: 'observe',
      },
      {
        id: 'navigation',
        title: 'Navigation',
        content: 'These 12 pages map to the full upstreaming workflow.',
        targetElement: '[data-testid=sidebar]',
        actionRequired: 'observe',
      },
      {
        id: 'submit_driver',
        title: 'Submit a Driver',
        content: 'Start by creating a migration task in Driver Migration Center.',
        targetElement: '[data-testid=submit-driver]',
        actionRequired: 'click',
      },
    ],
  },
  {
    id: 'approval_workflow',
    name: 'Understanding Approvals',
    trigger: 'manual',
    steps: [
      {
        id: 'approval_matrix',
        title: '3-Dimensional Approval',
        content: 'Patches pass lifecycle, subsystem, and quality checks before upstreaming.',
        targetElement: '[data-testid=approval-matrix]',
        actionRequired: 'observe',
      },
    ],
  },
]

const STORAGE_PREFIX = 'aura.teaching.completed.'

export function isFlowCompleted(flowId: string): boolean {
  return window.localStorage.getItem(`${STORAGE_PREFIX}${flowId}`) === '1'
}

export function markFlowCompleted(flowId: string): void {
  window.localStorage.setItem(`${STORAGE_PREFIX}${flowId}`, '1')
}
