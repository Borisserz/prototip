from crewai import Agent, Task

presentation_agent = Agent(
    role='Presentation Creator',
    goal='Assemble charts and insights into a cohesive PowerPoint presentation structure.',
    backstory='You are an executive assistant who creates perfect management presentations. You use top-down communication style.',
    verbose=True,
    allow_delegation=False
)

def create_presentation_task(topic: str) -> Task:
    return Task(
        description=f"Create a 5-slide presentation on the topic: '{topic}'.",
        expected_output="A structured list of slides with titles, bullet points, and required charts.",
        agent=presentation_agent
    )
