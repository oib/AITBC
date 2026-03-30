"""Genesis block generation commands for AITBC CLI"""

import click
import json
import yaml
from pathlib import Path
from datetime import datetime
from ..core.genesis_generator import GenesisGenerator, GenesisValidationError
from ..core.config import MultiChainConfig, load_multichain_config
from ..models.chain import GenesisConfig
from ..utils import output, error, success

@click.group()
def genesis():
    """Genesis block generation and management commands"""
    pass

@genesis.command()
@click.argument('config_file', type=click.Path(exists=True))
@click.option('--output', '-o', help='Output file path')
@click.option('--template', help='Use predefined template')
@click.option('--format', type=click.Choice(['json', 'yaml']), default='json', help='Output format')
@click.pass_context
def create(ctx, config_file, output, template, format):
    """Create genesis block from configuration"""
    try:
        config = load_multichain_config()
        generator = GenesisGenerator(config)
        
        if template:
            # Create from template
            genesis_block = generator.create_from_template(template, config_file)
        else:
            # Create from configuration file
            with open(config_file, 'r') as f:
                config_data = yaml.safe_load(f)
            
            genesis_config = GenesisConfig(**config_data['genesis'])
            genesis_block = generator.create_genesis(genesis_config)
        
        # Determine output file
        if output is None:
            chain_id = genesis_block.chain_id
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = f"genesis_{chain_id}_{timestamp}.{format}"
        
        # Save genesis block
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format == 'yaml':
            with open(output_path, 'w') as f:
                yaml.dump(genesis_block.dict(), f, default_flow_style=False, indent=2)
        else:
            with open(output_path, 'w') as f:
                json.dump(genesis_block.dict(), f, indent=2)
        
        success("Genesis block created successfully!")
        result = {
            "Chain ID": genesis_block.chain_id,
            "Chain Type": genesis_block.chain_type.value,
            "Purpose": genesis_block.purpose,
            "Name": genesis_block.name,
            "Genesis Hash": genesis_block.hash,
            "Output File": output,
            "Format": format
        }
        
        output(result, ctx.obj.get('output_format', 'table'))
        
        if genesis_block.privacy.visibility == "private":
            success("Private chain genesis created! Use access codes to invite participants.")
        
    except GenesisValidationError as e:
        error(f"Genesis validation error: {str(e)}")
        raise click.Abort()
    except Exception as e:
        error(f"Error creating genesis block: {str(e)}")
        raise click.Abort()

@genesis.command()
@click.argument('genesis_file', type=click.Path(exists=True))
@click.pass_context
def validate(ctx, genesis_file):
    """Validate genesis block integrity"""
    try:
        config = load_multichain_config()
        generator = GenesisGenerator(config)
        
        # Load genesis block
        genesis_path = Path(genesis_file)
        if genesis_path.suffix.lower() in ['.yaml', '.yml']:
            with open(genesis_path, 'r') as f:
                genesis_data = yaml.safe_load(f)
        else:
            with open(genesis_path, 'r') as f:
                genesis_data = json.load(f)
        
        from ..models.chain import GenesisBlock
        genesis_block = GenesisBlock(**genesis_data)
        
        # Validate genesis block
        validation_result = generator.validate_genesis(genesis_block)
        
        if validation_result.is_valid:
            success("Genesis block is valid!")
            
            # Show validation details
            checks_data = [
                {
                    "Check": check,
                    "Status": "✓ Pass" if passed else "✗ Fail"
                }
                for check, passed in validation_result.checks.items()
            ]
            
            output(checks_data, ctx.obj.get('output_format', 'table'), title="Validation Results")
        else:
            error("Genesis block validation failed!")
            
            # Show errors
            errors_data = [
                {
                    "Error": error_msg
                }
                for error_msg in validation_result.errors
            ]
            
            output(errors_data, ctx.obj.get('output_format', 'table'), title="Validation Errors")
            
            # Show failed checks
            failed_checks = [
                {
                    "Check": check,
                    "Status": "✗ Fail"
                }
                for check, passed in validation_result.checks.items()
                if not passed
            ]
            
            if failed_checks:
                output(failed_checks, ctx.obj.get('output_format', 'table'), title="Failed Checks")
            
            raise click.Abort()
        
    except Exception as e:
        error(f"Error validating genesis block: {str(e)}")
        raise click.Abort()

@genesis.command()
@click.argument('genesis_file', type=click.Path(exists=True))
@click.pass_context
def info(ctx, genesis_file):
    """Show genesis block information"""
    try:
        config = load_multichain_config()
        generator = GenesisGenerator(config)
        
        genesis_info = generator.get_genesis_info(genesis_file)
        
        # Basic information
        basic_info = {
            "Chain ID": genesis_info["chain_id"],
            "Chain Type": genesis_info["chain_type"],
            "Purpose": genesis_info["purpose"],
            "Name": genesis_info["name"],
            "Description": genesis_info.get("description", "No description"),
            "Created": genesis_info["created"],
            "Genesis Hash": genesis_info["genesis_hash"],
            "State Root": genesis_info["state_root"]
        }
        
        output(basic_info, ctx.obj.get('output_format', 'table'), title="Genesis Block Information")
        
        # Configuration details
        config_info = {
            "Consensus Algorithm": genesis_info["consensus_algorithm"],
            "Block Time": f"{genesis_info['block_time']}s",
            "Gas Limit": f"{genesis_info['gas_limit']:,}",
            "Gas Price": f"{genesis_info['gas_price'] / 1e9:.1f} gwei",
            "Accounts Count": genesis_info["accounts_count"],
            "Contracts Count": genesis_info["contracts_count"]
        }
        
        output(config_info, ctx.obj.get('output_format', 'table'), title="Configuration Details")
        
        # Privacy settings
        privacy_info = {
            "Visibility": genesis_info["privacy_visibility"],
            "Access Control": genesis_info["access_control"]
        }
        
        output(privacy_info, ctx.obj.get('output_format', 'table'), title="Privacy Settings")
        
        # File information
        file_info = {
            "File Size": f"{genesis_info['file_size']:,} bytes",
            "File Format": genesis_info["file_format"]
        }
        
        output(file_info, ctx.obj.get('output_format', 'table'), title="File Information")
        
    except Exception as e:
        error(f"Error getting genesis info: {str(e)}")
        raise click.Abort()

@genesis.command()
@click.argument('genesis_file', type=click.Path(exists=True))
@click.pass_context
def hash(ctx, genesis_file):
    """Calculate genesis hash"""
    try:
        config = load_multichain_config()
        generator = GenesisGenerator(config)
        
        genesis_hash = generator.calculate_genesis_hash(genesis_file)
        
        result = {
            "Genesis File": genesis_file,
            "Genesis Hash": genesis_hash
        }
        
        output(result, ctx.obj.get('output_format', 'table'))
        
    except Exception as e:
        error(f"Error calculating genesis hash: {str(e)}")
        raise click.Abort()

@genesis.command()
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def templates(ctx, format):
    """List available genesis templates"""
    try:
        config = load_multichain_config()
        generator = GenesisGenerator(config)
        
        templates = generator.list_templates()
        
        if not templates:
            output("No templates found", ctx.obj.get('output_format', 'table'))
            return
        
        if format == 'json':
            output(templates, ctx.obj.get('output_format', 'table'))
        else:
            templates_data = [
                {
                    "Template": template_name,
                    "Description": template_info["description"],
                    "Chain Type": template_info["chain_type"],
                    "Purpose": template_info["purpose"]
                }
                for template_name, template_info in templates.items()
            ]
            
            output(templates_data, ctx.obj.get('output_format', 'table'), title="Available Templates")
        
    except Exception as e:
        error(f"Error listing templates: {str(e)}")
        raise click.Abort()

@genesis.command()
@click.argument('template_name')
@click.option('--output', '-o', help='Output file path')
@click.pass_context
def template_info(ctx, template_name, output):
    """Show detailed information about a template"""
    try:
        config = load_multichain_config()
        generator = GenesisGenerator(config)
        
        templates = generator.list_templates()
        
        if template_name not in templates:
            error(f"Template {template_name} not found")
            raise click.Abort()
        
        template_info = templates[template_name]
        
        info_data = {
            "Template Name": template_name,
            "Description": template_info["description"],
            "Chain Type": template_info["chain_type"],
            "Purpose": template_info["purpose"],
            "File Path": template_info["file_path"]
        }
        
        output(info_data, ctx.obj.get('output_format', 'table'), title=f"Template Information: {template_name}")
        
        # Show template content if requested
        if output:
            template_path = Path(template_info["file_path"])
            if template_path.exists():
                with open(template_path, 'r') as f:
                    template_content = f.read()
                
                output_path = Path(output)
                output_path.write_text(template_content)
                success(f"Template content saved to {output}")
        
    except Exception as e:
        error(f"Error getting template info: {str(e)}")
        raise click.Abort()

@genesis.command()
@click.argument('chain_id')
@click.option('--format', type=click.Choice(['json', 'yaml']), default='json', help='Export format')
@click.option('--output', '-o', help='Output file path')
@click.pass_context
def export(ctx, chain_id, format, output):
    """Export genesis block for a chain"""
    try:
        config = load_multichain_config()
        generator = GenesisGenerator(config)
        
        genesis_data = generator.export_genesis(chain_id, format)
        
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            if format == 'yaml':
                # Parse JSON and convert to YAML
                parsed_data = json.loads(genesis_data)
                with open(output_path, 'w') as f:
                    yaml.dump(parsed_data, f, default_flow_style=False, indent=2)
            else:
                output_path.write_text(genesis_data)
            
            success(f"Genesis block exported to {output}")
        else:
            # Print to stdout
            if format == 'yaml':
                parsed_data = json.loads(genesis_data)
                output(yaml.dump(parsed_data, default_flow_style=False, indent=2), 
                      ctx.obj.get('output_format', 'table'))
            else:
                output(genesis_data, ctx.obj.get('output_format', 'table'))
        
    except Exception as e:
        error(f"Error exporting genesis block: {str(e)}")
        raise click.Abort()

@genesis.command()
@click.argument('template_name')
@click.argument('output_file')
@click.option('--format', type=click.Choice(['json', 'yaml']), default='yaml', help='Output format')
@click.pass_context
def create_template(ctx, template_name, output_file, format):
    """Create a new genesis template"""
    try:
        # Basic template structure
        template_data = {
            "description": f"Genesis template for {template_name}",
            "genesis": {
                "chain_type": "topic",
                "purpose": template_name,
                "name": f"{template_name.title()} Chain",
                "description": f"A {template_name} chain for AITBC",
                "consensus": {
                    "algorithm": "pos",
                    "block_time": 5,
                    "max_validators": 100,
                    "authorities": []
                },
                "privacy": {
                    "visibility": "public",
                    "access_control": "open",
                    "require_invitation": False
                },
                "parameters": {
                    "max_block_size": 1048576,
                    "max_gas_per_block": 10000000,
                    "min_gas_price": 1000000000,
                    "block_reward": "2000000000000000000"
                },
                "accounts": [],
                "contracts": []
            }
        }
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format == 'yaml':
            with open(output_path, 'w') as f:
                yaml.dump(template_data, f, default_flow_style=False, indent=2)
        else:
            with open(output_path, 'w') as f:
                json.dump(template_data, f, indent=2)
        
        success(f"Template created: {output_file}")
        
        result = {
            "Template Name": template_name,
            "Output File": output_file,
            "Format": format,
            "Chain Type": template_data["genesis"]["chain_type"],
            "Purpose": template_data["genesis"]["purpose"]
        }
        
        output(result, ctx.obj.get('output_format', 'table'))
        
    except Exception as e:
        error(f"Error creating template: {str(e)}")
        raise click.Abort()
