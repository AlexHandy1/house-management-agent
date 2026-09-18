# List of behaviours to review in evaluation

research cost tool focused
- if the agent receives an issue with not enough information to generate a cost estimate, it doesn't reach for the research_cost tool and asks for more information
- when a valid issue is reported, the agent always reaches for the research_cost tool to generate a cost estimate
- the research_cost tool always conducts a web search and finds 2+ sources to support its estimate
- the research_cost tool must return a total cost estimate - an absolute number and range 
- the research_cost tool must include a short explanation and rationale for its estimate
- the research_cost tool should articulate areas of uncertainty and where more information mgiht imrpove its estimate 
- the research_cost tool should not include extra narrative or generic explanation/commentary around why the costs might vary in circumstances not mentioned or relevant to the issue. For example, that emergency call outs are more expensive or how bills might be implemented ('engineers typically charge a call-out fee' or 'Manchester, is outside the London M25 zone. Regional pricing for Manchester averages above the national UK average for certain jobs, while official manufacturers apply standard non-London rates')
- the agent must only return content relevant to managing a rental property issue (adversarial cases)


## Backlog of ideas/requirements generated whilst building this but not immediately relevant

- ability to check status of an issue
- ability to review against previous costs and quotes
- whitelist guidance websites 
	- https://www.mybuilder.com/price-guides
	- https://www.checkatrade.com/blog/cost-guides/how-much-do-tradespeople-cost/
- intentionally not planning to build strict evals around assessing 'correctness' given context is all estimates will a soft reference for comparing real quotes from multiple contractors
	- this includes broad sampling to test for variability of estimate -> may come back to this