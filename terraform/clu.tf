terraform {
  required_providers {
    cudo = {
      source = "CudoVentures/cudo"
      version = "0.4.0"
    }
  }
}

variable "cudo_api_key" {
  description = "API key for Cudo provider"
  type        = string
}

variable "vllm_api_key" {
  description = "API key for VLLM server"
  type        = string
}

provider "cudo" {
  api_key   = var.cudo_api_key
  project_id = "speck-dev"
}

resource "cudo_vm" "speck-dev" {
  depends_on     = []
  id             = "speck-dev-1"
  machine_type   = "ice-lake-a40-compute"
  data_center_id = "se-stockholm-1"
  gpu_model = "A40 (compute mode)"
  gpus = 1
  memory_gib     = 16
  vcpus          = 4
  boot_disk = {
    image_id = "ubuntu-2204-nvidia-535-docker-v20240214"
    size_gib = 100
  }
  ssh_key_source = "user"
}

resource "null_resource" "copy_files" {
  depends_on = [cudo_vm.speck-dev]

  connection {
    type     = "ssh"
    user     = "root"
    host     = cudo_vm.speck-dev.external_ip_address
    private_key = file("~/.ssh/id_rsa")
  }

  provisioner "file" {
    source      = "scripts/docker-compose.yml"
    destination = "/root/docker-compose.yml"
  }

  provisioner "file" {
    source      = "scripts/nginx.conf"
    destination = "/root/nginx.conf"
  }
}

resource "null_resource" "run_commands" {
  depends_on = [null_resource.copy_files]

  connection {
    type     = "ssh"
    user     = "root"
    host     = cudo_vm.speck-dev.external_ip_address
    private_key = file("~/.ssh/id_rsa")
  }

  provisioner "remote-exec" {
    inline = [
      # Run certbot to generate SSL certificates using Docker
      <<EOT
      docker run \
        --rm \
        --name certbot \
        -p 80:80 \
        -v "/etc/letsencrypt:/etc/letsencrypt" \
        -v "/var/lib/letsencrypt:/var/lib/letsencrypt" \
        certbot/certbot \
        certonly \
        --standalone \
        --non-interactive \
        --agree-tos \
        -m andrew@gator.works \
        -d clu.myspeck.ai
      EOT
      ,
      
      # Start services with docker-compose
      "VLLM_API_KEY=${var.vllm_api_key} docker compose -f /root/docker-compose.yml up -d"
    ]
  }
}
