#!/usr/bin/env python3
"""Simple test script for import_config functionality without dependencies."""
import asyncio
import paramiko
import json
from pathlib import Path


async def test_import_config_simple():
    """Test import config directly with SSH."""
    hostname = '161.33.45.233'
    username = 'ubuntu'
    key_path = Path.home() / '.ssh' / 'rokkonch.key'

    print(f'Testing import_config from {hostname}...')
    print(f'Key path: {key_path}')
    print(f'Key exists: {key_path.exists()}')

    if not key_path.exists():
        print(f'Error: SSH key not found at {key_path}')
        return

    try:
        # Create SSH client
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        print(f'Connecting to {hostname}...')
        ssh.connect(hostname, username=username, key_filename=str(key_path))
        print('Connected successfully!')

        # Read config file
        config_path = '~/.openclaw/openclaw.json'
        print(f'Reading config from {config_path}...')

        stdin, stdout, stderr = ssh.exec_command(f'cat {config_path}')
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            error_output = stderr.read().decode()
            print(f'Error reading config (exit status {exit_status}): {error_output}')
            ssh.close()
            return {
                'success': False,
                'error': f'Config file not found or cannot be read (exit status {exit_status})',
                'config': None,
                'metadata': None,
                'warnings': []
            }

        config_content = stdout.read().decode()

        if not config_content.strip():
            print(f'Error: Config file is empty')
            ssh.close()
            return {
                'success': False,
                'error': 'Config file is empty',
                'config': None,
                'metadata': None,
                'warnings': []
            }

        # Parse JSON
        try:
            config = json.loads(config_content)
            print(f'Config parsed successfully!')
            print(f'Keys in config: {list(config.keys())}')

            # Get metadata
            metadata = {}
            warnings = []

            # Get file stats
            stdin, stdout, stderr = ssh.exec_command(f'stat -c "%Y %s %a" {config_path}')
            stat_output = stdout.read().decode().strip()
            if stat_output:
                parts = stat_output.split()
                if len(parts) >= 3:
                    metadata['modified_time'] = int(parts[0])
                    metadata['size'] = int(parts[1])
                    metadata['permissions'] = parts[2]

            # Check for required fields
            required_fields = ['agent', 'gateway', 'skills']
            missing_fields = [f for f in required_fields if f not in config]
            if missing_fields:
                warnings.append(f'Missing expected fields: {", ".join(missing_fields)}')

            result = {
                'success': True,
                'config': config,
                'metadata': metadata,
                'warnings': warnings
            }

            print(f'\n=== Import Result ===')
            print(f'Success: {result["success"]}')
            print(f'Metadata: {json.dumps(metadata, indent=2)}')
            if warnings:
                print(f'Warnings: {warnings}')
            print(f'\nConfig preview (first 500 chars):')
            print(json.dumps(config, indent=2)[:500] + '...')

            return result

        except json.JSONDecodeError as e:
            print(f'Error parsing JSON: {e}')
            print(f'First 200 chars of content: {config_content[:200]}')
            ssh.close()
            return {
                'success': False,
                'error': f'Invalid JSON in config file: {e}',
                'config': None,
                'metadata': None,
                'warnings': []
            }

        finally:
            ssh.close()
            print('\nSSH connection closed')

    except paramiko.AuthenticationException:
        print('Authentication failed')
        return {
            'success': False,
            'error': 'SSH authentication failed',
            'config': None,
            'metadata': None,
            'warnings': []
        }
    except paramiko.SSHException as e:
        print(f'SSH error: {e}')
        return {
            'success': False,
            'error': f'SSH connection error: {e}',
            'config': None,
            'metadata': None,
            'warnings': []
        }
    except Exception as e:
        print(f'Unexpected error: {e}')
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': f'Unexpected error: {e}',
            'config': None,
            'metadata': None,
            'warnings': []
        }


if __name__ == '__main__':
    result = asyncio.run(test_import_config_simple())
    print(f'\n=== Final Result ===')
    print(json.dumps(result, indent=2, ensure_ascii=False))
