# Defines all the tools used by the agent
from langchain.tools import StructuredTool
from .coverage import CoverageCenter
from service import SeedGenService

def create_viewfunction_tool(harness: str, service: SeedGenService) -> StructuredTool:
    def view(function_name: str) -> str:
        """
        Returns the source code of the given function.

        :param function_name: The name of the function to view.
        :return: The source code of the function.
        """
        locate_result = service.locate(harness, function_name)
        if locate_result is None:
            return "Function not found."
        
        filename, line = locate_result
        view_result = service.view(filename, int(line))
        if view_result is None:
            return "Failed to view function."

        return view_result

    return StructuredTool.from_function(view)


def create_run_generator_tool(
    harness: str,
    service: SeedGenService,
    coverage_center: CoverageCenter,
    script_id: int
) -> StructuredTool:
    def run(code: str) -> str:
        """
        Runs the given Python Script to generate test cases. Returns the coverage information of generated test cases. The Python script will be executed 50 times as `python3 /tmp/generator.py /tmp/generated_seedX`, where X is the seed number.

        :param code: The Python code to run.
        :return: The coverage information of generated test cases.
        """

        script_path = coverage_center.store_script(script_id, code)
        try:
            seed_files = coverage_center.generate_seeds(script_path)
        except RuntimeError as e:
            return str(e)

        coverage = service.run(harness, seed_files)
        if coverage is None:
            return "Failed to collect coverage."

        coverage_center.store_coverage_info(script_id, coverage)
        return coverage

    return StructuredTool.from_function(run)