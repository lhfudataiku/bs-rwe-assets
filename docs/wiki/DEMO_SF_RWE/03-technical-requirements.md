<div class="alert">
This is a demo only and thus should not be installed on customer instances.
</div>


This section informs you about all the requirements needed to use this project.

# Instance Requirements
This project is only compatible with instances with  **Dataiku V13.4+**.

# Code Environment
This project requires the code env solution_medical-report-analyser containing the following Python packages:
>MarkupSafe<2.2.0
Jinja2>=2.11,<3.2
cloudpickle>=1.3,<1.6
flask>=1.0,<2.3
itsdangerous<2.1.0
lightgbm>=3.2,<3.3
scikit-learn>=1.0,<1.6
scikit-optimize>=0.7,<=0.10.2
scipy>=1.13,<1.14
statsmodels>=0.12.2,<0.15
Werkzeug<3.1
xgboost>=1.5.1,<2
gluonts>=0.8.1,<0.16
pmdarima>=1.2.1,<2.1
mxnet>=1.8.0.post0,<1.10
prophet>=1.1.1,<1.2
lifelines==0.27.8
scikit-survival==0.22.1

# Solution Requirements
This project requires Dataiku's RWD Cohort Discovery Solution to be installed as the source for the required import datasets.