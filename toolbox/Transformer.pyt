"""ArcGIS Pro Python toolbox entry point for GMF.

This toolbox declares the ArcGIS Pro user interface only.  All workflow logic
is delegated to :mod:`transformer`, making the controller independently
testable outside ArcGIS Pro.
"""

from __future__ import annotations

import os
from typing import Sequence

import arcpy

import transformer as controller
from utils.constants import (
    EXECUTION_MODES,
    FC_MAPPING_FILE,
    FIELD_MAPPING_FILE,
    DOMAIN_MAPPING_FILE,
    LOOKUP_FILE,
    MODE_MIGRATE_ONLY,
    MODE_VALIDATE_AND_MIGRATE,
)


class Toolbox:
    """Define the Geodatabase Migration Framework ArcGIS Python toolbox.

    Args:
        None.

    Raises:
        None.

    Notes:
        ArcGIS Pro discovers this class automatically when the .pyt is added.
    """

    def __init__(self) -> None:
        """Initialize toolbox metadata and registered geoprocessing tools.

        Args:
            None.

        Returns:
            None.

        Raises:
            None.

        Notes:
            One top-level tool exposes the complete GMF lifecycle.
        """
        self.label = "Geodatabase Migration Framework"
        self.alias = "GMF"
        self.description = (
            "Migrates feature classes into a copied template geodatabase "
            "using validated CSV configuration rules."
        )
        self.tools = [GeodatabaseMigration]


class GeodatabaseMigration:
    """Expose the main Transformer controller as an ArcGIS Pro tool.

    Args:
        None.

    Raises:
        None.

    Notes:
        This class only maps ArcGIS parameter values to transformer.run.
    """

    def __init__(self) -> None:
        """Initialize tool metadata.

        Args:
            None.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Foreground execution keeps ArcGIS messages and progress visible.
        """
        self.label = "Geodatabase Migration"
        self.description = (
            "Validate configuration and migrate feature classes from a source "
            "geodatabase into an output copied from the template geodatabase."
        )
        self.canRunInBackground = False

    def getParameterInfo(self) -> Sequence[arcpy.Parameter]:
        """Create the ArcGIS Pro input and output parameter definitions.

        Args:
            None.

        Returns:
            Ordered ArcGIS parameter collection.

        Raises:
            None.

        Notes:
            Parameter order mirrors transformer.run input order where possible.
        """
        configuration_folder = arcpy.Parameter(
            displayName="Configuration Folder",
            name="configuration_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )

        source_gdb = arcpy.Parameter(
            displayName="Source GDB",
            name="source_gdb",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )

        template_gdb = arcpy.Parameter(
            displayName="Template GDB",
            name="template_gdb",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )

        output_gdb = arcpy.Parameter(
            displayName="Output GDB",
            name="output_gdb",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Output",
        )

        execution_mode = arcpy.Parameter(
            displayName="Execution Mode",
            name="execution_mode",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        execution_mode.filter.type = "ValueList"
        execution_mode.filter.list = list(EXECUTION_MODES)
        execution_mode.value = MODE_VALIDATE_AND_MIGRATE

        generate_log = arcpy.Parameter(
            displayName="Generate Log",
            name="generate_log",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        generate_log.value = True

        overwrite_output = arcpy.Parameter(
            displayName="Overwrite Output",
            name="overwrite_output",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        overwrite_output.value = False

        return [
            configuration_folder,
            source_gdb,
            template_gdb,
            output_gdb,
            execution_mode,
            generate_log,
            overwrite_output,
        ]

    def isLicensed(self) -> bool:
        """Return whether the tool may run with the current ArcGIS license.

        Args:
            None.

        Returns:
            Always ``True`` because GMF uses base ArcPy cursor operations.

        Raises:
            None.

        Notes:
            Environment-specific data permissions are validated at run time.
        """
        return True

    def updateParameters(self, parameters: Sequence[arcpy.Parameter]) -> None:
        """Apply responsive ArcGIS UI behavior to parameter values.

        Args:
            parameters: ArcGIS parameter collection.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Output remains visible in every mode so reports and logs have a
            deterministic sibling-folder location.
        """
        if parameters[4].valueAsText == "":
            parameters[4].value = MODE_VALIDATE_AND_MIGRATE

    def updateMessages(self, parameters: Sequence[arcpy.Parameter]) -> None:
        """Add early, non-mutating ArcGIS parameter validation messages.

        Args:
            parameters: ArcGIS parameter collection.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Deep schema and mapping checks belong to Validator after execution.
        """
        configuration_folder = parameters[0].valueAsText
        template_gdb = parameters[2].valueAsText
        output_gdb = parameters[3].valueAsText
        execution_mode = parameters[4].valueAsText

        if configuration_folder and os.path.isdir(configuration_folder):
            missing = [
                filename for filename in (FC_MAPPING_FILE, FIELD_MAPPING_FILE, DOMAIN_MAPPING_FILE, LOOKUP_FILE)
                if not os.path.isfile(os.path.join(configuration_folder, filename))
            ]
            if missing:
                parameters[0].setErrorMessage(
                    "Configuration Folder is missing required file(s): {}.".format(", ".join(missing))
                )

        if (
            execution_mode in {MODE_MIGRATE_ONLY, MODE_VALIDATE_AND_MIGRATE}
            and template_gdb and output_gdb
            and os.path.normcase(os.path.abspath(template_gdb)) == os.path.normcase(os.path.abspath(output_gdb))
        ):
            parameters[3].setErrorMessage(
                "Output GDB must be different from Template GDB to protect the template schema."
            )

    def execute(self, parameters: Sequence[arcpy.Parameter], messages: object) -> None:
        """Run the main Transformer controller from ArcGIS Pro values.

        Args:
            parameters: ArcGIS parameter collection in getParameterInfo order.
            messages: ArcGIS geoprocessing messages object.

        Returns:
            None.

        Raises:
            arcpy.ExecuteError: If controller returns a non-success status.

        Notes:
            Controller Logger messages already reach ArcGIS when Generate Log
            is selected.  This method adds concise final status and report links.
        """
        configuration_folder = parameters[0].valueAsText
        source_gdb = parameters[1].valueAsText
        template_gdb = parameters[2].valueAsText
        output_gdb = parameters[3].valueAsText
        execution_mode = parameters[4].valueAsText
        generate_log = bool(parameters[5].value)
        overwrite_output = bool(parameters[6].value)

        arcpy.AddMessage("=" * 70)
        arcpy.AddMessage("Geodatabase Migration Framework")
        arcpy.AddMessage("Execution mode: {}".format(execution_mode))
        arcpy.AddMessage("=" * 70)

        try:
            result = controller.run(
                configuration_folder=configuration_folder,
                source_gdb=source_gdb,
                template_gdb=template_gdb,
                output_gdb=output_gdb,
                execution_mode=execution_mode,
                overwrite_output=overwrite_output,
                generate_log=generate_log,
            )
        except Exception as error:
            arcpy.AddError("Unable to start GMF controller: {}".format(error))
            raise arcpy.ExecuteError

        if result.report_paths is not None:
            arcpy.AddMessage("Reports generated:")
            for report_path in result.report_paths.__dict__.values():
                arcpy.AddMessage("  {}".format(report_path))
        if result.log_path:
            arcpy.AddMessage("Migration log: {}".format(result.log_path))

        if result.succeeded:
            arcpy.AddMessage("GMF completed successfully: {}".format(result.message))
            if result.output_gdb:
                parameters[3].value = result.output_gdb
            return

        arcpy.AddError("GMF finished with status {}: {}".format(result.status.value, result.message))
        raise arcpy.ExecuteError
