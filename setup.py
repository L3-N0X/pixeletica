from setuptools import setup, find_packages

setup(
    name="pixeletica",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
)
