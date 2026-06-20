from crewai import Agent, Task

dashboard_agent = Agent(
    role='Dashboard Designer',
    goal='Compose analytical dashboards from various charts and KPIs using BI context.',
    backstory='You are an expert UI/UX dashboard designer for tax analytics. You know how to arrange horizontal_bars, donuts, and line charts into cohesive layouts.',
    verbose=True,
    allow_delegation=False
)

def create_dashboard_task(requirements: str) -> Task:
    return Task(
        description=f"Design a dashboard layout for: {requirements}. Pick 3-5 suitable charts.",
        expected_output="JSON specification for a dashboard layout with KPIs and charts.",
        agent=dashboard_agent
    )
