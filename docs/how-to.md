# How to

## How to model infrastructure

Doxa is designed to be flexible and extensible, but this also means that there are many ways to model the same real-world phenomenon. 

Let's define "infrastructure" as the physical and organizational structures needed for the operation of a society or enterprise, such as transportation networks, energy grids, communication systems, etc.

In such terms, infrastructure can be considered as a special type of resource that agents can invest in, trade, and utilize to produce other goods and services without being consumed in the process.

To do so, we can model infrastructure as a durable resource with the following characteristics:

- Not instantly consumed: Unlike raw materials, infrastructure is not consumed when used. Instead, it provides ongoing benefits or capabilities to agents. Therefore, an operation that utilizes infrastructure would not reduce its quantity in the agent's portfolio. 
An operation that requires infrastructure must have the infrastructure resource as an input (for example "military_basis": 1) and have the same infrastructure as an output (for example "military_basis": 1). This way, the engine will check if the agent has the required quantity of infrastructure to perform the operation, but it won't reduce it after the operation is executed.

- Investment and maintenance: Agents can invest in building or upgrading infrastructure, which would increase its quantity or quality. They can also allocate resources for maintenance to prevent degradation over time. This can be modeled as operations that increase the quantity of the infrastructure resource in the agent's portfolio.

## How to model technology

Technology can be modeled as a special type of resource that agents can invest in, trade, and utilize to produce other goods and services.
To model technology, we can define it as a resource with the following characteristics:

- Not directly usable: Technology itself is not consumed or directly used in production. Instead, it provides capabilities or efficiencies that enhance the production process. Therefore, an operation that utilizes technology would not reduce its quantity in the agent's portfolio. We'll define the technology as a resource with `consumable: false` in the YAML configuration and then place it as input of an operation. The engine will check if the agent has the required quantity of technology to perform the operation, but it won't reduce it after the operation is executed.  

## How to model labor

Labor can be modeled as a resource that agents can allocate to perform operations, produce goods and services, and earn income. To model labor, we can define it as a resource with the following characteristics:

- Consumable: Labor is consumed when used in production. Therefore, an operation that utilizes labor would reduce its quantity in the agent's portfolio. We'll define labor as a resource with `consumable: true` in the YAML configuration and then place it as input of an operation. The engine will check if the agent has the required quantity of labor to perform the operation, and it will reduce it after the operation is executed.

- Heterogeneous: Labor can have different skill levels, specializations, and productivity. We can model this by defining different types of labor resources (e.g., unskilled labor, skilled labor, managerial labor) with varying attributes and effects on production. This allows us to capture the diversity of the labor force and its impact on economic outcomes.

- Derived: Labor can be defined as a derived/calculated resource that is produced by other operations (e.g., education, training) and can be used as an input for production operations. This allows us to model the dynamics of the labor market and the effects of investments in human capital. Therefore it can be computed as "infrastructure * productivity" or similar, where education is a non-consumable resource that agents can invest in to increase their labor output over time.
