import pyredner
import torch
import math

class EnvironmentMap:
    def __init__(self, values, env_to_world = torch.eye(4, 4)):
        # Convert to constant texture if necessary
        if isinstance(values, torch.Tensor):
            values = pyredner.Texture(values)

        assert(values.texels.is_contiguous())
        assert(values.texels.dtype == torch.float32)
        if pyredner.get_use_gpu():
            assert(values.texels.is_cuda)
        else:
            assert(not values.texels.is_cuda)

        assert(env_to_world.dtype == torch.float32)

        # Build sampling table
        luminance = 0.212671 * values.texels[:, :, 0] + \
                    0.715160 * values.texels[:, :, 1] + \
                    0.072169 * values.texels[:, :, 2]
        # For each y, compute CDF over x
        sample_cdf_xs_ = torch.cumsum(luminance, dim = 1)
        y_weight = torch.sin(\
        	math.pi * (torch.arange(luminance.shape[0],
                dtype = torch.float32, device = luminance.device) + 0.5) \
             / float(luminance.shape[0]))
        # Compute CDF for x
        sample_cdf_ys_ = torch.cumsum(sample_cdf_xs_[:, -1] * y_weight, dim = 0)
        pdf_norm = (luminance.shape[0] * luminance.shape[1]) / \
        	(sample_cdf_ys_[-1].item() * (2 * math.pi * math.pi))
        # Normalize to [0, 1)
        sample_cdf_xs = (sample_cdf_xs_ - sample_cdf_xs_[:, 0:1]) / \
            torch.max(sample_cdf_xs_[:, (luminance.shape[1] - 1):luminance.shape[1]],
                1e-8 * torch.ones(sample_cdf_xs_.shape[0], 1, device = sample_cdf_ys_.device))
        sample_cdf_ys = (sample_cdf_ys_ - sample_cdf_ys_[0]) / \
            torch.max(sample_cdf_ys_[-1], torch.tensor([1e-8], device = sample_cdf_ys_.device))

        self.values = values
        self.env_to_world = env_to_world
        self.world_to_env = torch.inverse(env_to_world).contiguous()
        self.sample_cdf_ys = sample_cdf_ys.contiguous()
        self.sample_cdf_xs = sample_cdf_xs.contiguous()
        self.pdf_norm = pdf_norm

    def state_dict(self):
        return {
            'values': self.values.state_dict(),
            'env_to_world': self.env_to_world,
            'world_to_env': self.world_to_env,
            'sample_cdf_ys': self.sample_cdf_ys,
            'sample_cdf_xs': self.sample_cdf_xs,
            'pdf_norm': self.pdf_norm,
        }

    @classmethod
    def load_state_dict(cls, state_dict):
        out = cls.__new__(EnvironmentMap)
        out.values = pyredner.Texture.load_state_dict(state_dict['values'])
        out.env_to_world = state_dict['env_to_world']
        out.world_to_env = state_dict['world_to_env']
        out.sample_cdf_ys = state_dict['sample_cdf_ys']
        out.sample_cdf_xs = state_dict['sample_cdf_xs']
        out.pdf_norm = state_dict['pdf_norm']

        return out
