from setuptools import setup, find_packages

setup(
    name="your_project_name",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
)
