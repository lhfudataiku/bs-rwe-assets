This flow zone is where the input datasets are added to the project, and their schema is checked and conformed to the solution requirement. Data preparation and feature engineering steps should be done in a separate project to match the expected input datasets format illustrated in the following article: [Data Model & Files](article:3)
![flow-OMOP-tables.png](pxK0VKf23t6N)

Input datasets are selected and imported via [Project Setup](article:8). The pipeline involves an automatic datatype conversion and turns column names to upper case via prepare recipes. Review  [Data Model & Files](article:3) for all possible input datasets.


⚠️ The import datasets and the prepare recipes only appear after completing the Project Setup, [Import Datasets from DataPrep Project](scenario:IMPORTDATASETSFROMDATAPREPPROJECT). 