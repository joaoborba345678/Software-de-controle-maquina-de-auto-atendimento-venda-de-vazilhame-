import tkinter as tk
from PIL import Image, ImageTk
import pygame
import os
import json
import threading
import multiprocessing
import cv2
import numpy as np
import requests
import time
import RPi.GPIO as GPIO

# Importando ApiGateway de um módulo externo, ajuste conforme necessário
from payer import ApiGateway

class Camera:
    def __init__(self, camera_ip_address, gpio_pin, fixed_image_paths, capture_interval=5, gpio_active_time=1):
        self.camera_ip_address = camera_ip_address
        self.gpio_pin = gpio_pin
        self.fixed_image_paths = fixed_image_paths
        self.capture_interval = capture_interval
        self.gpio_active_time = gpio_active_time
        self.fixed_images = [cv2.imread(path) for path in fixed_image_paths]
        self.validate_images()
        self.setup_gpio()
        cv2.namedWindow("Imagem Capturada", cv2.WINDOW_NORMAL)
        self.capture_count = 0
        self.max_captures = 1

    def validate_images(self):
        for idx, image in enumerate(self.fixed_images):
            if image is None:
                raise ValueError(f"Erro ao carregar a imagem fixa {idx+1}. Verifique o caminho da imagem.")

    def setup_gpio(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.OUT)
        GPIO.output(self.gpio_pin, GPIO.HIGH)  # Garantir que o GPIO comece no estado DESLIGADO

    def capture_esp32cam_image(self):
        try:
            response = requests.get(f"http://{self.camera_ip_address}/capture")
            if response.status_code == 200:
                return cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
            else:
                print("Erro ao capturar imagem da câmera ESP32-CAM:", response.status_code)
                return None
        except Exception as e:
            print("Erro ao capturar imagem da câmera ESP32-CAM:", e)
            return None

    def trigger_gpio(self):
        print("Acionando GPIO")
        GPIO.output(self.gpio_pin, GPIO.LOW)
        time.sleep(self.gpio_active_time)
        GPIO.output(self.gpio_pin, GPIO.HIGH)

    def compare_images(self, new_image):
        for idx, fixed_image in enumerate(self.fixed_images):
            correlation = cv2.matchTemplate(new_image, fixed_image, cv2.TM_CCOEFF_NORMED)
            max_corr = np.max(correlation)
            if max_corr >= 0.70:
                print(f"Imagem {idx+1} reconhecida! Coeficiente de correlação: {max_corr:.2f}")
                return True
        print("Nenhuma imagem reconhecida.")
        return False

    def start(self, pipe):
        try:
            print("Aguardando comando para iniciar a comparação de imagens...")
            while True:
                if pipe.poll():
                    command = pipe.recv()
                    if command == 'c':
                        print("Comando recebido: Iniciar comparação de imagens")
                        self.capture_images()
                    elif command == 'q':
                        break

                new_image = self.capture_esp32cam_image()
                if new_image is not None and new_image.shape[0] > 0 and new_image.shape[1] > 0:
                    cv2.imshow("Imagem Capturada", new_image)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        finally:
            GPIO.cleanup()
            cv2.destroyAllWindows()

    def capture_images(self):
        print("Iniciando a comparação de imagens...")
        while self.capture_count < self.max_captures:
            new_image = self.capture_esp32cam_image()
            if new_image is not None and new_image.shape[0] > 0 and new_image.shape[1] > 0:
                cv2.imshow("Imagem Capturada", new_image)
                if not self.compare_images(new_image):  # If no image is recognized
                    self.trigger_gpio()
                self.capture_count += 1
                time.sleep(self.capture_interval)

## Código principal da câmera (modificado para multiprocessing)
def camera_process(pipe):
    camera_ip_address = "192.168.1.180"
    gpio_pin = 13
    fixed_image_paths = ["1.jpg", "2.jpg", "3.jpg", "4.jpg"]
    capture_interval = 2  # Intervalo de tempo entre capturas em segundos
    gpio_active_time = 20  # Tempo que o GPIO fica ativo em segundos

    camera = Camera(camera_ip_address, gpio_pin, fixed_image_paths, capture_interval=capture_interval, gpio_active_time=gpio_active_time)
    camera.start(pipe)

class Aplicativo:
    def __init__(self, root, camera_pipe):
        self.root = root
        self.camera_pipe = camera_pipe
        self.GPIO_PIN_19 = 19
        self.GPIO_PIN_26 = 26
        self.GPIO_PIN_20 = 20
        self.GPIO_PIN_21 = 21

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.GPIO_PIN_19, GPIO.OUT)
        GPIO.setup(self.GPIO_PIN_26, GPIO.OUT)
        GPIO.setup(self.GPIO_PIN_20, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.GPIO_PIN_21, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        root.title("Estacao gas 24hs")
        root.attributes('-fullscreen', True)
        pygame.mixer.init()

        self.imagens = {}
        self.carregar_imagens()

        self.telas = [
            {"tela": "Bemvindo.png", "som": "bemvindo.wav"},# tela 0:
            {"tela": "Selecao.png", "som": "Opcaodepagamento.wav"},# tela 1:
            {"tela": "Senha.png", "som": "Digiteasenha.wav"},# tela 2:
            {"tela": "Pagamento.png", "som": "Digiteasenha.wav"},# tela 3:
            {"tela": "Insiraobotijao.png", "som": "insiraobotijao.wav"},# tela 4:
            {"tela": "toque_em_avancar.png", "som": "retire.wav"},# tela 5:
            {"tela": "Analisando.png", "som": "Analisandobotijao.wav"},# tela 6:
            {"tela": "retirabotijao.png", "som": "agradecimento.wav"},# tela 7:
            #{"tela": "botijaorecusado.png", "som": "botijaorecusado.mp3"},# tela 8:
            #{"tela": "manutenção.png", "som": "agradecimento.wav"},# tela 9:
            #{"tela": "recarregandoequipamento.png", "som": "agradecimento.wav"},# tela 7:
            
            
            
        ]
        self.indice_tela_atual = 0
        self.som_terminado = True

        self.valor_pagamento_com_vasilhame = 0.0
        self.valor_pagamento_sem_vasilhame = 0.0
        self.senha_correta = "1234"
        self.valor_pagamento = 0.0

        self.carregar_valores_pagamento()

        self.exibir_tela()

        root.bind("<space>", self.fechar_aplicativo)
        self.verificar_gpio_periodicamente()

    def carregar_imagens(self):
        for tela in ["Bemvindo.png", "Selecao.png", "Senha.png", "Pagamento.png", "Insiraobotijao.png", "toque_em_avancar.png", "Analisando.png", "retirabotijao.png","botijaorecusado.png","manutenção.png", "recarregandoequipamento.png"]:
            caminho_imagem = os.path.join(os.getcwd(), tela)
            if os.path.exists(caminho_imagem):
                imagem = Image.open(caminho_imagem)
                imagem = imagem.resize((600, 800))
                imagem = imagem.rotate(0, expand=True)
                self.imagens[tela] = ImageTk.PhotoImage(imagem)
            else:
                print(f"Arquivo de imagem não encontrado: {caminho_imagem}")
                # Adicionar imagem padrão caso a imagem não seja encontrada
                imagem_padrao = Image.new('RGB', (600, 800), color = (73, 109, 137))
                self.imagens[tela] = ImageTk.PhotoImage(imagem_padrao)

    def carregar_valores_pagamento(self):
        try:
            with open('valores_pagamento.json', 'r') as f:
                dados = json.load(f)
                self.valor_pagamento_com_vasilhame = dados.get('valor_pagamento_com_vasilhame', 0.0)
                self.valor_pagamento_sem_vasilhame = dados.get('valor_pagamento_sem_vasilhame', 0.0)
        except (FileNotFoundError, json.JSONDecodeError):
            self.valor_pagamento_com_vasilhame = 0.0
            self.valor_pagamento_sem_vasilhame = 0.0

    def salvar_valores_pagamento(self):
        with open('valores_pagamento.json', 'w') as f:
            json.dump({
                'valor_pagamento_com_vasilhame': self.valor_pagamento_com_vasilhame,
                'valor_pagamento_sem_vasilhame': self.valor_pagamento_sem_vasilhame
            }, f)

    def exibir_tela(self):
        self.limpar_tela_anterior()

        imagem = self.imagens.get(self.telas[self.indice_tela_atual]["tela"])
        if imagem:
            self.canvas = tk.Canvas(self.root, width=imagem.width(), height=imagem.height())
            self.canvas.pack()
            self.canvas.create_image(0, 0, anchor=tk.NW, image=imagem)

            if self.indice_tela_atual == 0:
                self.canvas.bind("<Button-1>", lambda event: [self.reproduzir_som()])

            elif self.indice_tela_atual == 1:
                botao_com_vasilhame = tk.Button(self.canvas, text="C.V.", command=lambda: self.iniciar_contagem("com"))
                self.canvas.create_window(560, 770, anchor=tk.NW, window=botao_com_vasilhame)

                botao_sem_vasilhame = tk.Button(self.canvas, text="S.V.", command=lambda: self.iniciar_contagem("sem"))
                self.canvas.create_window(500, 770, anchor=tk.NW, window=botao_sem_vasilhame)

                self.adicionar_botoes_selecao()
                self.adicionar_botao_voltar()

            elif self.indice_tela_atual == 2:
                self.adicionar_botoes_pagamento()
                self.adicionar_botao_voltar()

            elif self.indice_tela_atual == 4:
                self.reproduzir_som("insiraobotijao.wav")

            elif self.indice_tela_atual == 5:
                botao_imagem = Image.open("avancar1.png").resize((200, 150))
                botao_imagem = ImageTk.PhotoImage(botao_imagem)
                botao = tk.Button(self.canvas, image=botao_imagem, command=lambda: [self.acionar_saida(self.GPIO_PIN_26), self.reproduzir_som("Analisandobotijao.wav"), self.camera_pipe.send('c')])
                botao.image = botao_imagem
                self.canvas.create_window(200, 450, anchor=tk.NW, window=botao)

            elif self.indice_tela_atual == 6:
                self.root.after(20000, lambda: [self.reproduzir_som("Retireobotijao.wav")])

            elif self.indice_tela_atual == 7:
                self.root.after(2000, lambda: [self.reproduzir_som("agradecimento.wav")])

    def adicionar_botoes_selecao(self):
        botoes = [
            {"imagem": "carga.png", "posicao": (240, 310), "texto": "VALOR", "valor": self.valor_pagamento_com_vasilhame, "comando": lambda: self.selecionar_valor_pagamento(self.valor_pagamento_com_vasilhame)},
            {"imagem": "botijao.png", "posicao": (240, 480), "texto": " VALOR", "valor": self.valor_pagamento_sem_vasilhame, "comando": lambda: self.selecionar_valor_pagamento(self.valor_pagamento_sem_vasilhame)}
        ]
        for botao_info in botoes:
            botao_imagem = Image.open(botao_info["imagem"]).resize((150, 120))
            botao_imagem = ImageTk.PhotoImage(botao_imagem)
            botao = tk.Button(self.canvas, image=botao_imagem, command=botao_info["comando"])
            botao.image = botao_imagem
            self.canvas.create_window(*botao_info["posicao"], anchor=tk.NW, window=botao)

            # Adicionando texto com o valor
            label_valor = tk.Label(self.canvas, text=f"{botao_info['texto']}: R${botao_info['valor']:.2f}", font=("Arial", 15, "bold"), bg="white", fg="black")
            self.canvas.create_window(botao_info["posicao"][0], botao_info["posicao"][1] + 130, anchor=tk.NW, window=label_valor)

    def selecionar_valor_pagamento(self, valor):
        self.valor_pagamento = valor
        self.reproduzir_som()

    def adicionar_botoes_pagamento(self):
        botoes = [
            {"imagem": "pix.png", "posicao": (250, 380), "comando": lambda: [self.reproduzir_som("aproxime cartao.wav"), self.executar_pagamento_pix()]},
            {"imagem": "credito.png", "posicao": (250, 440), "comando": lambda: [self.reproduzir_som("aproxime cartao.wav"), self.executar_pagamento_credito()]},
            {"imagem": "debito.png", "posicao": (250, 500), "comando": lambda: [self.reproduzir_som("aproxime cartao.wav"), self.executar_pagamento_debito()]},
        ]
        for botao_info in botoes:
            botao_imagem = Image.open(botao_info["imagem"]).resize((150, 50))
            botao_imagem = ImageTk.PhotoImage(botao_imagem)
            botao = tk.Button(self.canvas, image=botao_imagem, command=botao_info["comando"])
            botao.image = botao_imagem
            self.canvas.create_window(*botao_info["posicao"], anchor=tk.NW, window=botao)

    def adicionar_botao_voltar(self):
        botao_voltar_imagem = Image.open("VOLTAR.png").resize((100, 20))
        botao_voltar_imagem = ImageTk.PhotoImage(botao_voltar_imagem)
        botao_voltar = tk.Button(self.canvas, image=botao_voltar_imagem, command=self.voltar_tela)
        botao_voltar.image = botao_voltar_imagem
        self.canvas.create_window(5, 770, anchor=tk.NW, window=botao_voltar)

    def voltar_tela(self):
        if self.indice_tela_atual > 0:
            self.indice_tela_atual -= 1
            self.exibir_tela()

    def reproduzir_som(self, som=None):
        if self.som_terminado:
            try:
                if som is None:
                    caminho_som = self.telas[self.indice_tela_atual]["som"]
                else:
                    caminho_som = som
                som = pygame.mixer.Sound(caminho_som)
                som.play()
                self.som_terminado = False
                self.root.after(int(som.get_length() * 1000), self.avancar_tela)
            except Exception as e:
                print(f"Erro ao reproduzir som: {e}")
                self.avancar_tela()
        else:
            print("Aguarde o término do som anterior.")

    def avancar_tela(self):
        self.som_terminado = True
        self.indice_tela_atual += 1
        if self.indice_tela_atual >= len(self.telas):
            self.indice_tela_atual = 0
        self.exibir_tela()

    def limpar_tela_anterior(self):
        if hasattr(self, 'canvas'):
            self.canvas.destroy()

    def fechar_aplicativo(self, event):
        self.camera_pipe.send('q')
        self.root.destroy()

    def acionar_saida(self, pin):
        try:
            GPIO.output(pin, GPIO.LOW)  # Ligar a saída no pino especificado
            time.sleep(2)  # Manter a saída ligada por 2 segundos
            GPIO.output(pin, GPIO.HIGH)  # Desligar a saída
        except Exception as e:
            print(f"Erro ao acionar saída: {e}")

    def executar_pagamento(self, metodo, tipo):
        try:
            print(f"Tentando processar pagamento com método: {metodo}, tipo: {tipo}, valor: {self.valor_pagamento}")
            resultado = ApiGateway('config.json').payment(metodo, tipo, self.valor_pagamento)
            print(f"Resultado do pagamento: {resultado}")
            if resultado.upper() == 'APPROVED':
                print('Pagamento Efetuado')
                self.acionar_saida(self.GPIO_PIN_19)
                self.trocar_tela(3)  # Ir para a tela de pagamento aprovado
            else:
                print(f'Pagamento Não Efetuado! Motivo: {resultado}')
                self.trocar_tela(0)  # Mudar para a tela de pagamento reprovado
        except Exception as e:
            print(f"Erro ao processar pagamento: {e}")
            self.trocar_tela(0)  # Mudar para a tela de pagamento reprovado

    def executar_pagamento_pix(self):
        self.executar_pagamento('PIX', 'DEBIT')

    def executar_pagamento_credito(self):
        self.executar_pagamento('CARD', 'CREDIT')

    def executar_pagamento_debito(self):
        self.executar_pagamento('CARD', 'DEBIT')

    def trocar_tela(self, indice):
        self.indice_tela_atual = indice
        self.exibir_tela()

    def mudar_valor_pagamento(self, tipo):
        self.mostrar_teclado_virtual(tipo, is_password=True)

    def mostrar_teclado_virtual(self, tipo, is_password=False):
        TecladoVirtual(self.root, lambda valor: self.validar_senha(valor, tipo) if is_password else self.atualizar_valor_pagamento(valor, tipo), is_password=is_password)

    def validar_senha(self, senha, tipo):
        if senha == self.senha_correta:
            self.mostrar_teclado_virtual(tipo)
        else:
            tk.messagebox.showerror("Erro", "Senha incorreta!")

    def atualizar_valor_pagamento(self, valor, tipo):
        try:
            novo_valor = float(valor)
            if tipo == "com":
                self.valor_pagamento_com_vasilhame = novo_valor
            else:
                self.valor_pagamento_sem_vasilhame = novo_valor
            self.salvar_valores_pagamento()  # Salva os novos valores de pagamento
            tk.messagebox.showinfo("Sucesso", "Valor do pagamento atualizado com sucesso!")
        except ValueError:
            tk.messagebox.showwarning("Atenção", "Valor não foi atualizado. Entrada inválida.")

    def limpar_gpio(self):
        GPIO.cleanup()

    def iniciar_contagem(self, tipo):
        self.root.after(5000, lambda: self.mudar_valor_pagamento(tipo))

    def verificar_gpio_periodicamente(self):
        if GPIO.input(self.GPIO_PIN_20) == GPIO.LOW:
            if self.indice_tela_atual != 9:
                self.indice_tela_anterior = self.indice_tela_atual
                self.indice_tela_atual = 9
                self.exibir_tela()
        elif GPIO.input(self.GPIO_PIN_21) == GPIO.LOW:
            if self.indice_tela_atual != 10:
                self.indice_tela_anterior = self.indice_tela_atual
                self.indice_tela_atual = 10
                self.exibir_tela()
        else:
            if self.indice_tela_atual in [9,10]:
                self.indice_tela_atual = self.indice_tela_anterior
                self.exibir_tela()

        self.root.after(100, self.verificar_gpio_periodicamente)

    def iniciar_captura_camera(self):
        self.camera_pipe.send('c')

    def parar_captura_camera(self):
        self.camera_pipe.send('q')

if __name__ == "__main__":
    parent_conn, child_conn = multiprocessing.Pipe()
    p = multiprocessing.Process(target=camera_process, args=(child_conn,))
    p.start()

    root = tk.Tk()
    app = Aplicativo(root, parent_conn)

    root.mainloop()
    p.join()
